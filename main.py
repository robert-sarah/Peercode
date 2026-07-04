
"""
PeerCode - Real-time collaborative editor based on ExCo
This script launches ExCo and integrates PeerCode features
"""

import os
import sys
import traceback

# Add ExCo to Python path
EXCO_PATH = os.path.join(os.path.dirname(__file__), "ExCo-master")
sys.path.insert(0, EXCO_PATH)

# Import ExCo modules
import qt
import data
import settings
import functions
import components.fonts
import components.signaldispatcher
import components.processcontroller
import components.communicator
import components.thesquid
import gui.mainwindow

# Import PeerCode
from peercode.integration import PeerCodeManager


def parse_arguments():
    """Parse command line arguments (copied from ExCo's exco.py)"""
    import argparse

    def parse_file_list(files_string):
        return files_string.split(";")

    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument(
        "-v",
        "--version",
        action="version",
        version="PeerCode 0.1.0 (based on ExCo)",
    )
    arg_parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        default=False,
        dest="debug_mode",
        help="Enable debug mode.",
    )
    arg_parser.add_argument(
        "-l",
        "--logging",
        action="store_true",
        default=False,
        dest="logging_mode",
        help="Show the logging window on startup.",
    )
    arg_parser.add_argument(
        "-n",
        "--new",
        action="store_true",
        default=False,
        dest="new_document",
        help="Create a new document in the main window on startup.",
    )
    file_group = arg_parser.add_argument_group("input file options")
    file_group.add_argument(
        "-f",
        "--files",
        type=parse_file_list,
        help="List of files to open on startup, separated by semicolons.",
    )
    file_group.add_argument(
        "single_file", action="store", nargs="?", default=None, help="Single file to open."
    )
    return arg_parser.parse_args()


def main():
    """Main function for PeerCode"""
    options = parse_arguments()
    data.command_line_options = options
    if options.debug_mode == True:
        data.debug_mode = True
    else:
        try:
            functions.output_redirect()
        except:
            traceback.print_exc()
    if options.logging_mode == True:
        data.logging_mode = True
    file_arguments = options.files
    if options.single_file is not None:
        if file_arguments is not None:
            file_list = file_arguments.split(";")
            file_list.append(options.single_file)
            file_arguments = ";".join(file_list)
        else:
            file_arguments = [options.single_file]
    if file_arguments == [""]:
        file_arguments = None

    # Create Qt application
    app = qt.QApplication(sys.argv)
    data.application = app
    data.application.setStyle("Fusion")

    # Process control
    number_of_instances = components.processcontroller.check_opened_excos()
    if settings.get("open-new-files-in-open-instance"):
        if number_of_instances > 1 and file_arguments is not None:
            try:
                _data = {"command": "open", "arguments": file_arguments}
                fc = components.communicator.FileCommunicator("OPEN-IN-EXISTING-INSTANCE")
                fc.send_data(_data)
                return
            except:
                pass
        elif number_of_instances > 1:
            try:
                _data = {"command": "show", "arguments": None}
                fc = components.communicator.FileCommunicator("SHOW-OPEN-INSTANCE")
                fc.send_data(_data)
                return
            except:
                pass

    # Set default font
    components.fonts.set_application_font(
        settings.get("current_font_name"),
        settings.get("current_font_size"),
    )
    data.signal_dispatcher = components.signaldispatcher.GlobalSignalDispatcher()

    # Create main window
    main_window = gui.mainwindow.MainWindow(
        new_document=options.new_document,
        logging=data.logging_mode,
        file_arguments=file_arguments,
    )
    components.thesquid.TheSquid.init_objects(main_window)
    main_window.import_user_functions()

    # Initialize PeerCode and inject it into ExCo
    peercode_manager = PeerCodeManager.get_instance()
    peercode_manager.initialize(main_window)

    # Add PeerCode menu to the menu bar
    _add_peercode_menu(main_window)

    # Start the application already maximized so window controls and maximize buttons are visible
    main_window.show()
    qt.QTimer.singleShot(0, main_window.showMaximized)
    result = app.exec()
    functions.output_backup()
    sys.exit(result)


def _add_peercode_menu(main_window):
    """Add PeerCode menu to the main window's menu bar"""
    if not hasattr(main_window, "menubar"):
        return

    # Add a PeerCode menu after the existing menus
    import qt
    from gui.menu import Menu

    # We need to find where to insert the menu. First, let's get all current actions
    actions = main_window.menubar.actions()

    # Create PeerCode menu
    peercode_menu = Menu("&PeerCode", main_window.menubar)

    # Add "Show Panel" action
    show_panel_action = qt.QAction("Show PeerCode Panel", main_window)
    show_panel_action.setShortcut(qt.QKeySequence("Ctrl+Shift+P"))
    show_panel_action.triggered.connect(
        lambda: PeerCodeManager.get_instance().show_panel()
    )
    peercode_menu.addAction(show_panel_action)

    sync_project_action = qt.QAction("Sync Project", main_window)
    sync_project_action.triggered.connect(
        lambda: PeerCodeManager.get_instance().sync_project()
    )
    peercode_menu.addAction(sync_project_action)

    peercode_menu.addSeparator()

    # Add "About PeerCode" action
    about_action = qt.QAction("About PeerCode", main_window)
    about_action.triggered.connect(lambda: _show_about_dialog(main_window))
    peercode_menu.addAction(about_action)

    # Insert the menu into the menu bar
    if actions:
        main_window.menubar.insertMenu(actions[-1], peercode_menu)
    else:
        main_window.menubar.addMenu(peercode_menu)


def _show_about_dialog(parent):
    """Show the about dialog for PeerCode"""
    import qt

    qt.QMessageBox.about(
        parent,
        "About PeerCode",
        """
        <h2>PeerCode</h2>
        <p>Real-time collaborative editing extension for ExCo</p>
        <p>Version 0.1.0</p>
        <p>Created By Levi Enama</p>
        <p>Based on ExCo by Matic Kukovec</p>
        """,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        print("\nFull stack trace:")
        traceback.print_exc()
        input("\nPress Enter to exit...")

