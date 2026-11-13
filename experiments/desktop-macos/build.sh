#!/bin/sh
set -eu
if [ "$#" -ne 2 ]; then echo "usage: build.sh WEB_DIST APP_BUNDLE" >&2; exit 2; fi
web=$1; app=$2
rm -rf "$app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources/web"
cp "$(dirname "$0")/Info.plist" "$app/Contents/Info.plist"
cp -R "$web/." "$app/Contents/Resources/web/"
python3 - "$app/Contents/Resources/web/index.html" <<'PY'
import re,sys
from pathlib import Path
p=Path(sys.argv[1])
text=p.read_text(encoding='utf-8')
text=re.sub(r'(?P<q>["\'])/(?!/)', lambda m:m.group('q')+'./', text)
p.write_text(text,encoding='utf-8')
PY
xcrun swiftc -O -framework Cocoa -framework WebKit "$(dirname "$0")/main.swift" -o "$app/Contents/MacOS/NEXDesktop"
