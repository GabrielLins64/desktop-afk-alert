# Build the working checkout with makepkg from the repository root.
pkgname=desktop-afk-alert
pkgver=0.1.3
pkgrel=1
pkgdesc='Keep your desktop visible. Warn unexpected visitors.'
arch=('any')
url='https://github.com/GabrielLins64/desktop-afk-alert'
license=('MIT')
depends=(
  'python>=3.11'
  'pyside6>=6.8'
  'python-evdev>=1.9'
  'python-pyudev>=0.24'
  'python-httpx>=0.28'
  'python-keyring>=25'
  'python-secretstorage>=3.3'
  'python-pywayland>=0.4.18'
  'python-jeepney>=0.9'
  'qt6-multimedia'
  'qt6-svg'
  'qt6-wayland'
  'libxcb'
  'libxkbcommon'
  'libxkbcommon-x11'
  'libxrandr'
  'pam'
  'sudo'
  'systemd'
  'ttf-dejavu'
  'xdg-desktop-portal'
)
makedepends=('python-build' 'python-installer' 'python-hatchling')
optdepends=(
  'gnome-keyring: remember alert credentials with Secret Service'
  'kwallet: remember alert credentials with Secret Service on KDE'
  'xdg-desktop-portal-gnome: desktop inhibition on GNOME'
  'xdg-desktop-portal-kde: desktop inhibition on KDE'
)

# The default makepkg srcdir would overlap this checkout's source directory.
# Keep local builds separate while respecting a custom BUILDDIR.
if [[ "$BUILDDIR" -ef "$startdir" ]]; then
  BUILDDIR="$startdir/build/makepkg"
fi

prepare() {
  # Package the current checkout, including uncommitted source changes.
  rm -rf -- "$srcdir/$pkgname"
  mkdir -p "$srcdir/$pkgname"
  cp -a "$startdir"/{LICENSE,README.md,pyproject.toml,resources,src} "$srcdir/$pkgname/"
  cp "$startdir/packaging/arch/desktop-afk-alert-helper" "$srcdir/$pkgname/"
}

build() {
  cd "$srcdir/$pkgname"
  python -m build --wheel --no-isolation
}

package() {
  cd "$srcdir/$pkgname"
  python -m installer --destdir="$pkgdir" dist/*.whl
  install -Dm755 desktop-afk-alert-helper "$pkgdir/usr/libexec/desktop-afk-alert-helper"
  install -Dm644 resources/desktop-afk-alert.desktop "$pkgdir/usr/share/applications/desktop-afk-alert.desktop"
  install -Dm644 resources/desktop-afk-alert.svg "$pkgdir/usr/share/icons/hicolor/scalable/apps/desktop-afk-alert.svg"
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
  install -Dm644 README.md "$pkgdir/usr/share/doc/$pkgname/README.md"
}
