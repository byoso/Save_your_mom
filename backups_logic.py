from pathlib import Path
import shutil


class BackupLogicError(Exception):
	pass


def _expand(path: str) -> Path:
	return Path(path).expanduser().resolve()


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


def _copy_directory_content(source: Path, destination: Path) -> None:
	for child in source.iterdir():
		dst = destination / child.name
		if child.is_dir():
			shutil.copytree(child, dst)
		else:
			shutil.copy2(child, dst)


def _prepare_destination(
	source: Path,
	destination: Path,
	destination_parent_guard: Path,
	overwrite: bool,
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
		if overwrite:
			_clear_directory_content(destination)
	else:
		destination.mkdir(parents=True, exist_ok=True)


def copy_local_to_target(
	local_path: str,
	target_path: str,
	media_path: str,
	overwrite: bool = True,
) -> None:
	source = _expand(local_path)
	destination = _expand(target_path)
	media_root = _expand(media_path)

	_assert_source_directory(source)
	if not media_root.exists() or not media_root.is_dir():
		raise BackupLogicError(f"Media path is invalid: {media_root}")

	_prepare_destination(source, destination, media_root, overwrite, "Target path")
	_copy_directory_content(source, destination)


def copy_target_to_local(
	target_path: str,
	local_path: str,
	user_home: str | None = None,
	overwrite: bool = True,
) -> None:
	source = _expand(target_path)
	destination = _expand(local_path)
	home_root = _expand(user_home) if user_home else Path.home().resolve()

	_assert_source_directory(source)
	_prepare_destination(source, destination, home_root, overwrite, "Local path")
	_copy_directory_content(source, destination)
