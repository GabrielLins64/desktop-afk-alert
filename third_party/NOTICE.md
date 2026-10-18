# Third-party software

Desktop AFK Alert's own code is MIT licensed. Its standalone GUI dynamically
links Qt, PySide6, Shiboken, and Qt's FFmpeg backend. Those components retain their
upstream copyrights and licenses; the application does not relicense them.

Qt, PySide6, and Shiboken are Copyright The Qt Company Ltd. and their respective
contributors. The LGPL version 3 and GPL version 3 license texts are included in
this directory. Qt's LGPL FFmpeg backend and other bundled LGPL libraries use
their respective LGPL terms; the LGPL 2.1 text is included as well. Additional
upstream notices from Python wheels are copied beside the compiled applications.

The exact Python dependency versions are recorded in `uv.lock` and in each
standalone directory's `third-party-licenses/INDEX.txt`. Corresponding upstream
source and notices are available from:

- Qt and PySide: https://download.qt.io/official_releases/QtForPython/
- Qt library source: https://download.qt.io/official_releases/qt/
- Qt FFmpeg source packages: https://download.qt.io/development_releases/prebuilt/ffmpeg/
- Qt third-party notices: https://doc.qt.io/qt-6/licenses-used-in-qt.html
- CPython: https://www.python.org/downloads/source/
- Other Python packages: the source distributions for the versions in `uv.lock`
  are available from https://pypi.org/.

The build uses upstream libraries without source modifications and preserves
separate shared libraries. Users may replace compatible LGPL shared libraries
in the standalone directory and rebuild the application using the public build
instructions. No application term restricts reverse engineering or modification
for debugging changes to these libraries. Administrator access is required to
replace files installed under `/opt`; development builds can be used without
replacing system-installed files.
