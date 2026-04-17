from pathlib import Path
from collections.abc import Callable
import errno
import os
import re
import shutil
from uuid import uuid4


class BackupLogicError(Exception):
	pass


COLLISION_MODE_AUTO = "auto"

RENAME_REASON_CASE = "Case-insensitive filesystem collision"
RENAME_REASON_TYPE = "Type conflict: file vs directory"
RENAME_REASON_LENGTH = "Name too long for destination filesystem"
RENAME_REASON_PATH_TOO_LONG = "Full path too long for destination filesystem"
RENAME_REASON_FORBIDDEN_CHARS = "Forbidden characters for FAT/NTFS/exFAT filesystem"

# Characters forbidden on NTFS / exFAT / FAT32.
_NTFS_FORBIDDEN_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Windows reserved device names (case-insensitive, with or without extension).
_NTFS_RESERVED_RE = re.compile(
    r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$', re.IGNORECASE
)


def _sanitize_for_fat(name: str) -> str:
    """Replace NTFS/exFAT forbidden characters and reserved names in a filename.
    Returns the sanitised name (unchanged if already clean)."""
    sanitized = _NTFS_FORBIDDEN_RE.sub("_", name)
    # Strip trailing dots and spaces (forbidden on NTFS).
    sanitized = sanitized.rstrip(". ")
    if not sanitized:
        sanitized = "_"
    if _NTFS_RESERVED_RE.match(sanitized):
        sanitized = f"_{sanitized}"
    return sanitized


def _normalized_name(name: str) -> str:
	return name.casefold()


def _with_uuid_suffix(name: str, is_dir: bool) -> str:
	suffix = uuid4().hex[:8]
	if is_dir:
		return f"{name}_{suffix}"
	path = Path(name)
	if path.suffix:
		return f"{path.stem}_{suffix}{path.suffix}"
	return f"{name}_{suffix}"


def _truncate_utf8(text: str, max_bytes: int) -> str:
	if max_bytes <= 0:
		return ""
	encoded = text.encode("utf-8")
	if len(encoded) <= max_bytes:
		return text
	trimmed = encoded[:max_bytes]
	while trimmed:
		try:
			return trimmed.decode("utf-8")
		except UnicodeDecodeError:
			trimmed = trimmed[:-1]
	return ""


def _name_max_bytes_for_dir(directory: Path) -> int:
	try:
		value = os.pathconf(str(directory), "PC_NAME_MAX")
		if isinstance(value, int) and value > 0:
			return value
	except (OSError, ValueError, AttributeError):
		pass
	return 255


def _safe_copy2(src: Path, dst: Path, original_name: str, renames: list) -> None:
	"""Attempt shutil.copy2; on ENAMETOOLONG add an incident report and skip."""
	try:
		shutil.copy2(src, dst)
	except OSError as exc:
		if exc.errno == errno.ENAMETOOLONG:
			renames.append((RENAME_REASON_PATH_TOO_LONG, original_name, str(dst)))
		else:
			raise


def _with_uuid_suffix_fitted(name: str, is_dir: bool, max_name_bytes: int) -> str:
	suffix = f"_{uuid4().hex[:8]}"
	if is_dir:
		base_budget = max_name_bytes - len(suffix.encode("utf-8"))
		base_name = _truncate_utf8(name, base_budget)
		if not base_name:
			base_name = "x"
		return f"{base_name}{suffix}"

	path = Path(name)
	ext = path.suffix
	ext_budget = len(ext.encode("utf-8"))
	base_budget = max_name_bytes - len(suffix.encode("utf-8")) - ext_budget
	base_name = _truncate_utf8(path.stem, base_budget)
	if not base_name:
		base_name = "x"
	result = f"{base_name}{suffix}{ext}"
	if len(result.encode("utf-8")) > max_name_bytes:
		result = _truncate_utf8(result, max_name_bytes)
	if not result:
		result = "x"
	return result


def _expand(path: str) -> Path:
	return Path(path).expanduser().resolve()


def _is_case_sensitive_fs(path: Path) -> bool:
	"""Test whether the filesystem at `path` is case-sensitive.
	Creates a temporary probe file inside `path` and tries to open it
	using an uppercase variant of the name.
	Returns True if case-sensitive, False if case-insensitive (exFAT, etc.).
	Falls back to False on any unexpected I/O error.
	`path` must point to an existing directory.
	"""
	probe_name = f".sym_test_{uuid4().hex}"
	probe = path / probe_name
	try:
		probe.touch()
		upper_probe = path / probe_name.upper()
		try:
			upper_probe.open("r").close()
			# Uppercase variant opened → case-insensitive FS.
			return False
		except FileNotFoundError:
			# Uppercase variant not found → case-sensitive FS.
			return True
		except OSError:
			return False
	except OSError:
		return False
	finally:
		probe.unlink(missing_ok=True)


def _is_within(path: Path, parent: Path) -> bool:
	try:
		path.relative_to(parent)
		return True
	except ValueError:
		return False


def _assert_source_directory(source: Path) -> None:
	if not source.exists() or not source.is_dir():
		raise BackupLogicError(f"Source path does not exist: {source}")


def _clear_directory_content(directory: Path) -> None:
	for child in directory.iterdir():
		if child.is_dir():
			shutil.rmtree(child)
		else:
			child.unlink()


def _build_dest_name_map(destination: Path) -> dict[str, Path]:
	"""Build a case-insensitive map of existing names in destination.
	Key: normalised (casefolded) name, Value: actual existing Path."""
	return {
		_normalized_name(child.name): child
		for child in destination.iterdir()
	}


def _copy_directory_merge(
	source: Path,
	destination: Path,
	case_sensitive: bool,
	renames: list,
	on_file_progress: Callable[[str], None] | None = None,
	skip_dir_names: set[str] | None = None,
) -> None:
	"""Recursive copy in merge mode.
	Rules:
	  - file   → no existing dest:     copy.
	  - file   → existing file (same casefold): copy only if size or mtime differs.
	  - file   → existing dir:         rename incoming file with UUID suffix, then copy.
	  - dir    → no existing dest:     mkdir + recurse.
	  - dir    → existing dir (same casefold): recurse (merge).
	  - dir    → existing file:        rename incoming dir with UUID suffix, mkdir, recurse.
	Case-insensitive collision between two source siblings (Toto/toto) is handled by
	renaming the second one with a UUID suffix on the destination side.
	"""
	dest_name_map = _build_dest_name_map(destination)
	# Track all normalised names already committed so far (pre-existing + already written).
	used_normalized: set[str] = set(dest_name_map.keys())

	for child in source.iterdir():
		if child.is_dir() and skip_dir_names and child.name in skip_dir_names:
			continue

		name_max_bytes = _name_max_bytes_for_dir(destination)
		entry_name = child.name
		if len(entry_name.encode("utf-8")) > name_max_bytes:
			entry_name = _with_uuid_suffix_fitted(child.name, child.is_dir(), name_max_bytes)
			renames.append((RENAME_REASON_LENGTH, child.name, entry_name))

		if not case_sensitive:
			sanitized = _sanitize_for_fat(entry_name)
			if sanitized != entry_name:
				renames.append((RENAME_REASON_FORBIDDEN_CHARS, entry_name, sanitized))
				entry_name = sanitized

		normalized_child = _normalized_name(entry_name)
		# On case-sensitive FS, only exact-name matches count for collisions.
		if case_sensitive:
			existing = destination / entry_name if (destination / entry_name).exists() else None
		else:
			existing = dest_name_map.get(normalized_child)

		if child.is_dir():
			if existing is None:
				# New dir: check no sibling collision from this batch (only on case-insensitive FS).
				if not case_sensitive and normalized_child in used_normalized:
					# A previously-written sibling claimed this normalised name: rename.
					resolved_name = _with_uuid_suffix_fitted(entry_name, is_dir=True, max_name_bytes=name_max_bytes)
					dst = destination / resolved_name
					dst.mkdir(parents=True, exist_ok=False)
					used_normalized.add(_normalized_name(resolved_name))
					renames.append((RENAME_REASON_CASE, entry_name, resolved_name))
					_copy_directory_merge(child, dst, case_sensitive, renames, on_file_progress, skip_dir_names)
				else:
					dst = destination / entry_name
					dst.mkdir(parents=True, exist_ok=False)
					used_normalized.add(normalized_child)
					_copy_directory_merge(child, dst, case_sensitive, renames, on_file_progress, skip_dir_names)
			elif existing.is_dir():
				# Dir → existing dir: merge recursively.
				_copy_directory_merge(child, existing, case_sensitive, renames, on_file_progress, skip_dir_names)
			else:
				# Dir vs existing file: rename incoming dir with UUID suffix.
				resolved_name = _with_uuid_suffix_fitted(entry_name, is_dir=True, max_name_bytes=name_max_bytes)
				dst = destination / resolved_name
				dst.mkdir(parents=True, exist_ok=False)
				used_normalized.add(_normalized_name(resolved_name))
				renames.append((RENAME_REASON_TYPE, entry_name, resolved_name))
				_copy_directory_merge(child, dst, case_sensitive, renames, on_file_progress, skip_dir_names)

		else:
			# Source is a file.
			if existing is None:
				if not case_sensitive and normalized_child in used_normalized:
					# Sibling collision (e.g. Toto already written): rename file.
					resolved_name = _with_uuid_suffix_fitted(entry_name, is_dir=False, max_name_bytes=name_max_bytes)
					dst = destination / resolved_name
					used_normalized.add(_normalized_name(resolved_name))
					renames.append((RENAME_REASON_CASE, entry_name, resolved_name))
					if on_file_progress:
						on_file_progress(resolved_name)
					_safe_copy2(child, dst, child.name, renames)
				else:
					dst = destination / entry_name
					used_normalized.add(normalized_child)
					if on_file_progress:
						on_file_progress(entry_name)
					_safe_copy2(child, dst, child.name, renames)
			elif existing.is_file():
				# File → existing file: replace only when size or mtime changed.
				src_stat = child.stat()
				dst_stat = existing.stat()
				if (
					src_stat.st_size != dst_stat.st_size
					or src_stat.st_mtime_ns != dst_stat.st_mtime_ns
				):
					if on_file_progress:
						on_file_progress(entry_name)
					_safe_copy2(child, existing, child.name, renames)
			else:
				# File vs existing dir: rename incoming file with UUID suffix.
				resolved_name = _with_uuid_suffix_fitted(entry_name, is_dir=False, max_name_bytes=name_max_bytes)
				dst = destination / resolved_name
				used_normalized.add(_normalized_name(resolved_name))
				renames.append((RENAME_REASON_TYPE, entry_name, resolved_name))
				if on_file_progress:
					on_file_progress(resolved_name)
				_safe_copy2(child, dst, child.name, renames)


def _copy_directory_legacy(
	source: Path,
	destination: Path,
	case_sensitive: bool,
	renames: list,
	on_file_progress: Callable[[str], None] | None = None,
	skip_dir_names: set[str] | None = None,
) -> None:
	"""Recursive copy in legacy mode (destination was purged beforehand).
	Still handles case-insensitive name collisions among source siblings."""
	used_normalized: set[str] = set()

	for child in source.iterdir():
		if child.is_dir() and skip_dir_names and child.name in skip_dir_names:
			continue

		name_max_bytes = _name_max_bytes_for_dir(destination)
		entry_name = child.name
		if len(entry_name.encode("utf-8")) > name_max_bytes:
			entry_name = _with_uuid_suffix_fitted(child.name, child.is_dir(), name_max_bytes)
			renames.append((RENAME_REASON_LENGTH, child.name, entry_name))

		if not case_sensitive:
			sanitized = _sanitize_for_fat(entry_name)
			if sanitized != entry_name:
				renames.append((RENAME_REASON_FORBIDDEN_CHARS, entry_name, sanitized))
				entry_name = sanitized

		normalized_child = _normalized_name(entry_name)
		if not case_sensitive and normalized_child in used_normalized:
			# Case-sibling collision: rename with UUID suffix.
			resolved_name = _with_uuid_suffix_fitted(entry_name, is_dir=child.is_dir(), max_name_bytes=name_max_bytes)
			dst = destination / resolved_name
			used_normalized.add(_normalized_name(resolved_name))
			renames.append((RENAME_REASON_CASE, entry_name, resolved_name))
		else:
			resolved_name = entry_name
			dst = destination / resolved_name
			used_normalized.add(normalized_child)

		if child.is_dir():
			dst.mkdir(parents=True, exist_ok=False)
			_copy_directory_legacy(child, dst, case_sensitive, renames, on_file_progress, skip_dir_names)
		else:
			if on_file_progress:
				on_file_progress(resolved_name)
			_safe_copy2(child, dst, child.name, renames)


def _prepare_destination(
	source: Path,
	destination: Path,
	destination_parent_guard: Path,
	merge_mode: bool,
	destination_label: str,
) -> None:
	if not _is_within(destination, destination_parent_guard):
		raise BackupLogicError(
			f"{destination_label} must be inside: {destination_parent_guard}"
		)

	if source == destination:
		raise BackupLogicError("Source and destination are identical")

	if _is_within(destination, source) or _is_within(source, destination):
		raise BackupLogicError("Source and destination cannot be nested")

	destination.parent.mkdir(parents=True, exist_ok=True)

	if destination.exists():
		if not destination.is_dir():
			raise BackupLogicError(f"Destination is not a directory: {destination}")
		if not merge_mode:
			# Legacy: wipe destination before copy.
			_clear_directory_content(destination)
	else:
		destination.mkdir(parents=True, exist_ok=True)


def copy_local_to_target(
	local_path: str,
	target_path: str,
	media_path: str,
	merge_mode: bool = True,
	on_file_progress: Callable[[str], None] | None = None,
) -> list:
	"""Copy local_path content to target_path.

	merge_mode=True (default): merge destination, overwrite same filename only when size or mtime differs.
	merge_mode=False: purge destination before copy (legacy behaviour).
	Returns a list of (reason, original_name, final_name) tuples for any renames that occurred.
	"""
	source = _expand(local_path)
	destination = _expand(target_path)
	media_root = _expand(media_path)

	_assert_source_directory(source)
	if not media_root.exists() or not media_root.is_dir():
		raise BackupLogicError(f"Media path is invalid: {media_root}")

	_prepare_destination(source, destination, media_root, merge_mode, "Target path")

	db_dir = media_root / ".save_your_mom"
	case_sensitive = _is_case_sensitive_fs(db_dir) if db_dir.is_dir() else True
	renames: list = []
	skipped_dir_names = {".save_your_mom"}

	if merge_mode:
		_copy_directory_merge(source, destination, case_sensitive, renames, on_file_progress, skipped_dir_names)
	else:
		_copy_directory_legacy(source, destination, case_sensitive, renames, on_file_progress, skipped_dir_names)

	return renames


def copy_target_to_local(
	target_path: str,
	local_path: str,
	user_home: str | None = None,
	merge_mode: bool = True,
	on_file_progress: Callable[[str], None] | None = None,
) -> list:
	"""Restore target_path content to local_path.

	merge_mode=True (default): merge destination, overwrite same filename only when size or mtime differs.
	merge_mode=False: purge destination before copy (legacy behaviour).
	Returns a list of (reason, original_name, final_name) tuples for any renames that occurred.
	"""
	source = _expand(target_path)
	destination = _expand(local_path)
	home_root = _expand(user_home) if user_home else Path.home().resolve()

	_assert_source_directory(source)
	_prepare_destination(source, destination, home_root, merge_mode, "Local path")

	# For local path, test FS sensitivity at the destination's parent.
	case_sensitive = _is_case_sensitive_fs(destination.parent)
	renames: list = []
	skipped_dir_names = {".save_your_mom"}

	if merge_mode:
		_copy_directory_merge(source, destination, case_sensitive, renames, on_file_progress, skipped_dir_names)
	else:
		_copy_directory_legacy(source, destination, case_sensitive, renames, on_file_progress, skipped_dir_names)

	return renames
