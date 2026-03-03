#!/usr/bin/env bash
# install.sh — download and install murmur from the latest GitHub release.
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/24R0qu3/Murmur/main/install.sh | bash
#   INSTALL_DIR=/usr/local/bin bash install.sh   # custom location (needs sudo)
set -euo pipefail

REPO="24R0qu3/Murmur"
BIN_NAME="murmur"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"

# ── Detect platform ──────────────────────────────────────────────────────────
OS="$(uname -s)"
ARCH="$(uname -m)"
case "$OS-$ARCH" in
  Linux-x86_64)   ARTIFACT="murmur-linux-x86_64"  ;;
  Darwin-arm64)   ARTIFACT="murmur-macos-arm64"  ;;
  Darwin-x86_64)  ARTIFACT="murmur-macos-arm64"  ;;  # runs via Rosetta 2
  *)
    echo "Unsupported platform: $OS $ARCH" >&2
    echo "Install from source: https://github.com/$REPO" >&2
    exit 1
    ;;
esac

# ── Resolve latest release tag ───────────────────────────────────────────────
echo "Fetching latest release info..."
TAG="$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
  | grep '"tag_name"' | head -1 \
  | sed 's/.*"tag_name": *"\([^"]*\)".*/\1/')"

if [ -z "$TAG" ]; then
  echo "Could not determine latest release tag." >&2
  exit 1
fi

# ── Download binary ──────────────────────────────────────────────────────────
URL="https://github.com/$REPO/releases/download/$TAG/$ARTIFACT"
echo "Downloading $BIN_NAME $TAG ($ARTIFACT)..."

mkdir -p "$INSTALL_DIR"
curl -fsSL "$URL" -o "$INSTALL_DIR/$BIN_NAME"
chmod +x "$INSTALL_DIR/$BIN_NAME"

echo "Installed to $INSTALL_DIR/$BIN_NAME"

# ── PATH hint ────────────────────────────────────────────────────────────────
if ! echo ":$PATH:" | grep -q ":$INSTALL_DIR:"; then
  echo ""
  echo "  $INSTALL_DIR is not in your PATH."
  echo "  Add it by running:"
  echo ""
  echo "    echo 'export PATH=\"$INSTALL_DIR:\$PATH\"' >> ~/.bashrc  # bash"
  echo "    echo 'export PATH=\"$INSTALL_DIR:\$PATH\"' >> ~/.zshrc   # zsh"
  echo ""
  echo "  Then restart your terminal."
fi

echo "Done. Run: $BIN_NAME"
