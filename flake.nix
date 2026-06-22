{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
  };

  outputs =
    inputs@{
      self,
      nixpkgs,
      flake-parts,
    }:
    let
      rosettakit =
        {
          lib,
          python3Packages,
        }:
        python3Packages.buildPythonPackage {
          name = "rosettakit";
          format = "pyproject";

          src =
            with lib.fileset;
            toSource {
              root = ./.;
              fileset = unions [
                ./LICENSE
                ./README.md
                ./pyproject.toml
                ./uv.lock
                ./rosettakit
              ];
            };

          build-system = with python3Packages; [ uv-build ];

          pythonImportsCheck = [ "rosettakit" ];
        };
    in
    flake-parts.lib.mkFlake { inherit inputs; } {
      systems = [
        "aarch64-darwin"
        "aarch64-linux"
        "x86_64-darwin"
        "x86_64-linux"
      ];

      perSystem =
        {
          pkgs,
          self',
          ...
        }:
        let
          rosettakitPackage = pkgs.callPackage rosettakit { };
        in
        {
          packages = {
            default = rosettakitPackage;
            rosettakit = rosettakitPackage;
          };
          checks.default = self'.packages.default;
          formatter = pkgs.nixfmt-tree;

          devShells.default = pkgs.mkShell {
            nativeBuildInputs = with pkgs; [
              tcl
              uv
            ];

            shellHook = ''
              export UV_CACHE_DIR="''${UV_CACHE_DIR:-$PWD/.uv-cache}"
            '';
          };
        };
    };
}
