#!/bin/bash
# Creates a minimal macOS .app bundle that runs the expander
APP_DIR="$HOME/Applications/TextExpander.app"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

cat > "$APP_DIR/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>TextExpander</string>
    <key>CFBundleIdentifier</key>
    <string>com.textexpander.client</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleExecutable</key>
    <string>run</string>
    <key>LSBackgroundOnly</key>
    <true/>
</dict>
</plist>
PLIST

cat > "$APP_DIR/Contents/MacOS/run" << 'SCRIPT'
#!/bin/bash
exec /usr/bin/python3 /Users/danielbaum/textexpander/client/expander.py
SCRIPT
chmod +x "$APP_DIR/Contents/MacOS/run"

echo "Created $APP_DIR"
echo ""
echo "Now:"
echo "1. Open System Settings → Privacy & Security → Accessibility"
echo "2. Click + and add ~/Applications/TextExpander.app"
echo "3. Then run:  open ~/Applications/TextExpander.app"
