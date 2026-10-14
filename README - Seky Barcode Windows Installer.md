# Seky Barcode Windows installer

## What the installer contains

The Windows app uses an Electron window and a self-contained Python backend executable. Python is not needed on a computer that only installs and runs the app. The barcode and Excel libraries are bundled locally, so those features do not rely on the Internet.

The installed app binds its local service to this computer only. It does not expose the database service to the local network.

## Existing database migration and storage

On first launch, the app looks for the previous database at:

`%USERPROFILE%\Desktop\Seky Barcode APP\SekyBarcode.sqlite3`

It migrates only if `%APPDATA%\SekyBarcode\SekyBarcode.sqlite3` does not already exist. The migration uses SQLite's backup API, so committed data in the old database's `-wal` file is included. The source `.sqlite3`, `-wal`, and `-shm` files are left untouched. Close the old app and server before first launch so the database is not being changed during migration. If the old project folder is somewhere else, move it to the Desktop location above before the first launch.

The new database and its SQLite sidecar files are stored under:

`%APPDATA%\SekyBarcode`

Database snapshots are kept in `%APPDATA%\SekyBarcode\database_backups`. Reinstalling or updating the app does not overwrite this folder, and uninstalling the app is configured to leave it in place. Use **Backup JSON** in the app before transferring records to another computer.

## Install and run

1. Open File Explorer and go to `Desktop > Seky Barcode APP > release`.
2. Double-click `SekyBarcode-Setup.exe`.
3. In the installer, click **Next**, keep or choose the install folder, click **Install**, then **Finish**. The app launches after installation and a desktop shortcut is created.
4. If you see a Windows warning that the publisher is unknown, the installer is unsigned because no signing certificate was supplied. Continue only if this is the installer you built from this project and the filename is `SekyBarcode-Setup.exe`.

The installed app runs without Python or an Internet connection.

## Build the installer yourself

This is needed only to rebuild the installer. Install Node.js 22.12 or newer and Python 3.10 or newer on the build computer. Node.js includes npm. Open PowerShell and run:

```powershell
npm install --global pnpm
cd "$HOME\Desktop\Seky Barcode APP"
pnpm install
pnpm run dist:win
```

The build script uses PyInstaller to package the backend. It installs the pinned PyInstaller version if needed. The finished installer is:

`release\SekyBarcode-Setup.exe`

## Test checklist

### 1. Install

- Double-click `release\SekyBarcode-Setup.exe`.
- Complete the installer and confirm that **Seky Barcode** appears in the Start menu and on the desktop.
- Open the app and confirm its window appears without opening a browser or command prompt.

### 2. Generate a barcode

- Enter a product name and price.
- Click **Generate Code & Add Item to Log**.
- Confirm the label preview shows the product and barcode and that the item appears once in the Log table.
- Try adding an existing product name or code and confirm the duplicate validation rejects it.

### 3. Save and reopen

- Close the app using its window close button.
- Open **Seky Barcode** from the desktop shortcut or Start menu.
- Confirm the item is still in the Log table.
- Confirm the database exists at `%APPDATA%\SekyBarcode\SekyBarcode.sqlite3`.

### 4. Update or reinstall

- Keep the app's database folder in place.
- Run a newer `SekyBarcode-Setup.exe` over the existing installation, or uninstall and install it again.
- Launch the app and confirm the item is still present.

Do not delete the database's `-wal` or `-shm` files manually. Use the app's JSON backup and restore controls to move data between computers.
