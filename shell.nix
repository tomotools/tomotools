# https://nixos.org/manual/nixpkgs/stable/#how-to-consume-python-modules-using-pip-in-a-virtual-environment-like-i-am-used-to-on-other-operating-systems
with import <nixpkgs> { };
pkgs.mkShell rec {
  name = "venv";
  venvDir = "./.venv";
  buildInputs = [
    python39Packages.python
    python39Packages.venvShellHook
    python39Packages.numpy
    python39Packages.pandas
  ];

  postVenvCreation = ''
    unset SOURCE_DATE_EPOCH
  '';

  postShellHook = ''
    unset SOURCE_DATE_EPOCH
  '';
}
