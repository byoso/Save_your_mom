# Save Your Mom !

Your Mom (like mine) is struggling to make her backups ? Ok, let's simplify this with an application.


# how it works

Run the app, you know what to do, it is simple... Just play a bit with it before trying this on your mom's PC to understand the basics.

# Behind the hood

"Save Your Mom" uses 2 very tiny databases, one is local, and one is created on each media registered in a file named ".save_your_mom.json" (so yes, 1 local DB + 1 in each Media registered)

The local DB contains the Medias registered, the one on the Media contains the paths of the saves.

## ok but why the hell 2 databases ?

Well, my mom's old PC will probably give its last breath soon... So, with the database stored in the media, instead of recreating each parametered saves manually, I'll just add the already existing media in the app, and magically, all the path for the saves are back.



Don't thank me, your mom's will.