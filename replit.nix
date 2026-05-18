
{ pkgs }: {
  deps = [
    pkgs.glibcLocales
    pkgs.freetype
    pkgs.python311
    pkgs.python311Packages.pip
    pkgs.gtk3
    pkgs.webkitgtk
    pkgs.pkg-config
  ];
}
