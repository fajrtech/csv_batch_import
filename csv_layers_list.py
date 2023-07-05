from PyQt5.QtWidgets import QTreeWidgetItem, QFileDialog, QAction
from PyQt5.QtCore import Qt
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.PyQt.QtWidgets import QAction, QDialog
from qgis.gui import QgsProjectionSelectionDialog, QgsMessageBar
from qgis.core import QgsVectorLayer, QgsProject, QgsLayerTreeGroup, QgsLayerTreeLayer, QgsCoordinateReferenceSystem

import os.path
import csv
# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .csv_layers_list_dialog import CsvLayersListDialog


class CsvLayersList:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        # keep full path
        self.path = ''
        # keep part of path not in the tree
        self.remaining_path = ''
        # keep all csv files chosen by user
        self.csv_lst = []
        # Keep all folder that will be added to group tree
        self.dir_list = []
        # store x coordinate
        self.x_field = ''
        # store y coordinate
        self.y_field = ''
        # store recent crs
        self.recent_crs_lst = []
        # create root of tree
        self.root_group = QgsProject.instance().layerTreeRoot()

        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'CsvLayersList_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&CSV Batch Import')

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('CsvLayersList', message)

    def add_action(
            self,
            icon_path,
            text,
            callback,
            enabled_flag=True,
            add_to_menu=True,
            add_to_toolbar=True,
            status_tip=None,
            whats_this=None,
            parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToVectorMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/csv_layers_list/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'CSV Batch Import'),
            callback=self.run,
            parent=self.iface.mainWindow())

        # will be set False in run()
        self.first_start = True

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginVectorMenu(
                self.tr(u'&CSV Batch Import'),
                action)
            self.iface.removeToolBarIcon(action)

    def get_full_path_for_tree_item(self, item):
        """The function constructs the full_path of given item by joining
         the remaining_path (defined in the class) with the path_to_toplevel."""
        parents_list = []
        parent_item = item.parent()

        while parent_item is not None:
            # insert parent_item at index 0
            parents_list.insert(0, parent_item)
            parent_item = parent_item.parent()

        # iterating over (prnt) in parents_list and apply the expression prnt.text(0) to it to convert to text
        text_parents_list = [prnt.text(0) for prnt in parents_list]

        # get path of item to toplevel item from text_parents_list
        path_to_toplevel = os.path.normpath(os.path.join(os.path.sep.join(text_parents_list), item.text(0)))
        # get full path of item
        full_path = os.path.normpath(os.path.join(self.remaining_path, path_to_toplevel))

        return full_path

    def get_dirs_files(self, dir_path):
        """The function retrieve the directories and files in the given directory
        then breaks out of the loop after the first iteration"""
        directories_list = []
        files_list = []
        # loop through the given path to get its children (directories/files)
        for root, dirs, files in os.walk(dir_path):
            for directory in dirs:
                directories_list.append(os.path.normpath(os.path.join(root, directory)))

            for file in files:
                files_list.append(os.path.normpath(os.path.join(root, file)))

            break
        return directories_list, files_list

    def add_subdir_and_subfiles(self, item):
        """ the function recursively adds subdirectories and files to the tree item,and set their check state and
        background color. It also adds the full path of the files to self.csvLst if not exist.."""
        full_path_item = self.get_full_path_for_tree_item(item)
        # by default add all
        self.dir_list.append(full_path_item)

        dir_list, files_list = self.get_dirs_files(full_path_item)

        # recursively add dir and sub dir
        for directory in dir_list:
            # convert directory name to item
            child_item = QTreeWidgetItem([os.path.basename(directory)])
            # add it to its parent in csv tree
            item.addChild(child_item)
            # make it check-able
            child_item.setFlags(child_item.flags() | Qt.ItemIsUserCheckable)
            # set it's state ny default to checked
            child_item.setCheckState(0, Qt.Checked)
            # set background color
            child_item.setBackground(0, QColor(233, 236, 239))

            self.add_subdir_and_subfiles(child_item)

        for file in files_list:
            # filter csv & tsv files only
            if file.endswith(('.csv', '.tsv')):
                # convert file name to item
                child_item = QTreeWidgetItem([os.path.basename(file)])
                #  add it to its parent as a child
                item.addChild(child_item)
                # make it check-able
                child_item.setFlags(child_item.flags() | Qt.ItemIsUserCheckable)
                #  set it's state to checked
                child_item.setCheckState(0, Qt.Checked)
                # set background color
                child_item.setBackground(0, QColor(248, 249, 250))

                # get full path child & add it to csv list
                child_full_path = self.get_full_path_for_tree_item(child_item)
                # add child path to csvLst if not exist
                if child_full_path not in self.csv_lst:
                    self.csv_lst.append(child_full_path)

    def evt_browse_btn_clicked(self):
        """The function allows the user to select a directory, populates the csv_tree with subdirectories and files
        under the selected directory, and gets the column names from the first CSV file to populate the QComboBoxes."""
        self.y_field = self.dlg.yfield_cmbBox.clear()
        self.x_field = self.dlg.xfield_cmbBox.clear()
        self.dir_list = []
        self.csv_lst = []
        # get full path and base name and the remaining path outside tree
        self.path = selected_directory = QFileDialog.getExistingDirectory(None, 'Select Directory', self.path)

        if selected_directory:
            selected_directory = os.path.normpath(selected_directory)
            self.dlg.rootDirLineEdit.setText(selected_directory)
            # clear previous Qtree
            self.dlg.csv_tree.clear()

            basename = os.path.basename(selected_directory)
            self.remaining_path = os.path.dirname(self.path)

            # convert directory name to item & add it as top level of tree
            top_level_item = QTreeWidgetItem([basename])
            self.dlg.csv_tree.addTopLevelItem(top_level_item)
            # make it check-able
            top_level_item.setFlags(top_level_item.flags() | Qt.ItemIsUserCheckable)
            #  set it's state to checked
            top_level_item.setCheckState(0, Qt.Checked)
            # set background color to color of dir
            top_level_item.setBackground(0, QColor(233, 236, 239))
            # recursively add subdirectories and files to the selected dir
            self.add_subdir_and_subfiles(top_level_item)

            if not self.csv_lst:
                # if there's no CSV/TSV files under the selected dir
                self.iface.messageBar().pushMessage('No CSV or TSV file under this directory!', level=1)
                return
            else:
                header_list = None
                i = 0
                while header_list is None and i < len(self.csv_lst):
                    # if there's at least 1 CSV/TSV file open it, & get the columns names
                    csv_file_path = self.csv_lst[i]
                    with open(csv_file_path, "r", newline="") as file:
                        reader = csv.reader(file)
                        header_list = next(reader, None)
                    i += 1

                if header_list is not None:
                    # Add the column names to the QComboBox
                    self.dlg.xfield_cmbBox.addItems(header_list)
                    self.dlg.yfield_cmbBox.addItems(header_list)
        else:
            self.dlg.rootDirLineEdit.setPlaceholderText('Please select a directory')
            self.iface.messageBar().pushMessage('Please select a directory', level=1)

    def file_is_valid(self, fpath):
        """The function checks if file is valid as a layer or not, and also return a layer if it's valid"""
        # get crs from combobox as str then convert to QgsCoordinateReferenceSystem obj then get .authid()
        crs = QgsCoordinateReferenceSystem(self.dlg.crs_cmbBox.currentText().split(' - ')[0]).authid()

        file_name = os.path.basename(fpath)
        name = os.path.splitext(file_name)[0]
        extension = os.path.splitext(file_name)[1]

        # check file type and change delimiter accordingly
        if extension == '.csv':
            delimiter = ','
        elif extension == '.tsv':
            delimiter = '\\t'

        # get uri & convert file to vector layer
        uri = f"file:///{fpath}?delimiter={delimiter}&crs={crs}&xField={self.x_field}&yField={self.y_field}"
        layer = QgsVectorLayer(uri, name, 'delimitedtext')

        if layer.isValid():
            # add layer to canvas without displaying it the tree
            QgsProject.instance().addMapLayer(layer, False)
            return True, layer
        else:
            return False, None

    def build_tree_from_paths(self, paths_list):
        """The function populates node tree based on the provided paths chosen by user,
        it creates group nodes for directories and adding vector layers for CSV/TSV files,
        based on the hierarchical structure of the paths, using the full path as a unique identifier"""
        # handle if only one file is selected
        if len(self.csv_lst) == 1:
            top_level_path = os.path.normpath(os.path.dirname(self.csv_lst[0]))
        else:
            # find the common path among all the paths
            top_level_path = os.path.normpath(os.path.commonpath(self.csv_lst))
        # get base name of path
        top_level_name = os.path.basename(top_level_path)
        # convert it to node
        top_level_node = QgsLayerTreeGroup(top_level_name)

        # Create a dictionary to store path as key and its node as value (node_dict[path] = node)
        node_dict = {top_level_path: top_level_node}

        # loop over each path in paths_list
        for path in paths_list:
            # keep a copy un-altered
            path_copy = path
            isvalid, layer = self.file_is_valid(path)
            # handle if coordinates doesn't match with the file
            if not isvalid:
                message = f"Can't load file {path}, Please check it's coordinates"
                self.iface.messageBar().pushMessage(message, level=1)
            # coordinates match with the file
            else:
                # handle if only one file is selected
                if len(self.csv_lst) == 1:
                    comp_lst = [os.path.basename(path_copy)]
                else:
                    # Split the path into components with seperator => top level path
                    components = path.split(top_level_path)
                    # get the part that will be added to our tree
                    path = components[1]

                    # Split the path again into components with new sep ==> \\
                    comp_lst = list(path.split(os.path.sep))
                    # remove '' from list to get each directory name as item [dir1, dir2, ... file.txt]
                    comp_lst.remove('')

                # handle if only one file is selected
                # set initial root path
                if len(self.csv_lst) == 1:
                    comp_path = os.path.dirname(path_copy)
                else:
                    comp_path = top_level_path
                # set initial node as top level
                prnt_node = top_level_node
                # loop over components list
                for c in comp_lst:
                    # join top path and comp
                    comp_path = os.path.join(comp_path, c)
                    # check if comp path is dir and not in node_dict
                    if os.path.isdir(comp_path) and comp_path not in node_dict:
                        # add path as key & node as value
                        node_dict[comp_path] = QgsLayerTreeGroup(c)
                        # add current node to parent node
                        prnt_node.addChildNode(node_dict[comp_path])
                        # set child node as parent for next loop
                        prnt_node = node_dict[comp_path]
                    # check if comp path is in node_dict
                    elif comp_path in node_dict:
                        # set child node as parent for next loop
                        prnt_node = node_dict[comp_path]
                    # check if comp path is file (last item in comp_lst)
                    elif os.path.isfile(comp_path):
                        if len(self.csv_lst) == 1:
                            prnt_dir = top_level_path
                        else:
                            # get parent directory path from file path
                            prnt_dir = os.path.dirname(path_copy)
                        # get the corresponding value to key/(parent path) from node dic
                        prnt_node = node_dict[prnt_dir]
                        # convert layer to node
                        layer_node = QgsLayerTreeLayer(layer)
                        # add layer ti its parent directory
                        prnt_node.addChildNode(layer_node)
        # clear node_dict & csv_lst
        node_dict.clear()
        self.csv_lst = []
        self.root_group.addChildNode(top_level_node)

    def evt_run_btn_clicked(self):
        """The function checks if valid coordinate fields and CSV files are selected.
        If so, it uses CSV file list to build the tree structure"""
        # get coordinates name in file by user
        self.x_field = self.dlg.xfield_cmbBox.currentText()
        self.y_field = self.dlg.yfield_cmbBox.currentText()

        # if there's coordinate values & files in csvLst
        if self.x_field and self.y_field and self.csv_lst:
            # temp list to carry directories contain csv/tsv files
            new_dir_list = []
            for directory in self.dir_list:
                # get children files for each directory in dir_list
                files_lst = self.get_dirs_files(directory)[1]
                # check if there is at least one file with the '.csv' or '.tsv' extension
                if any('.csv' in file or '.tsv' in file for file in files_lst):
                    # add directory to temp list
                    new_dir_list.append(directory)

            # set the temp list as dir_list
            self.dir_list = new_dir_list
            # send CSV files list (csvLst) & use it to build tree
            self.build_tree_from_paths(self.csv_lst)
        else:
            #  # if there's no coordinate values or files in csvLst
            self.iface.messageBar().pushMessage(
                'Please make sure there\'s CSV files with valid coordinates beneath this path', level=1)
            # clear selected directories
            self.csv_lst = []
            self.dir_list = []
            return

        # close dialog window
        self.dlg.close()

    def evt_crs_btn_clicked(self):
        """The function allows the user to select a CRS from the QgsProjectionSelectionDialog
        and updates the combo box's current text accordingly."""
        dialog = QgsProjectionSelectionDialog()
        result = dialog.exec_()

        crs = dialog.crs()
        crs_description = QgsCoordinateReferenceSystem(crs).description()
        crs_authid = QgsCoordinateReferenceSystem(crs).authid()

        # check if there's CRS selected or not
        if crs_description and crs_authid and result == QDialog.Accepted:
            index = self.dlg.crs_cmbBox.findText(crs_authid + ' - ' + crs_description)
            # check if item exists in the combo box
            if index != -1:
                self.dlg.crs_cmbBox.setCurrentText(crs_authid + ' - ' + crs_description)
            else:
                self.dlg.crs_cmbBox.addItem(crs_authid + ' - ' + crs_description)
                self.dlg.crs_cmbBox.setCurrentText(crs_authid + ' - ' + crs_description)

    def evt_itm_selected(self, item):
        """The function manages the selection of items in the tree and updates the corresponding
        lists (dir_list or csvLst) based on the checked or unchecked state of the items."""
        # get item's full path
        full_path = self.get_full_path_for_tree_item(item)

        # if item selected is a file
        if os.path.isfile(full_path):
            # if file is checked & its path doesn't exist in csvLst
            if item.checkState(0) == Qt.Checked and full_path not in self.csv_lst:
                # add its path to csvLst
                self.csv_lst.append(full_path)

            # if file is unchecked & its path exists in csvLst
            elif item.checkState(0) == Qt.Unchecked and full_path in self.csv_lst:
                # remove its path from csvLst
                self.csv_lst.remove(full_path)

        # if item selected is a directory
        elif os.path.isdir(full_path):
            # if directory is unchecked & its path exist in dir_list
            if item.checkState(0) == Qt.Unchecked and full_path in self.dir_list:
                # remove path & its children recursively from dir_list
                self.dir_unchecked(item)

            # if directory is checked & its path doesn't exist in dir_list
            if item.checkState(0) == Qt.Checked and full_path not in self.dir_list:
                # add path & its children recursively from dir_list
                self.dir_checked(item)

    def dir_checked(self, item):
        """The function adds the checked directory and its children to the corresponding lists
        (dir_list and csvLst) and recursively checks all child items under the directory"""
        # get item's full path
        item_path = self.get_full_path_for_tree_item(item)

        # check if item path checked is dir and if not in dir_list
        if os.path.isdir(item_path) and item_path not in self.dir_list:
            # add directory path to dir_list
            self.dir_list.append(item_path)

        # loop on item's children recursively
        for i in range(item.childCount()):
            child_item = item.child(i)
            # get full path of child
            child_full_path = self.get_full_path_for_tree_item(child_item)

            # if it's file add it to csv list
            if os.path.isfile(child_full_path) and child_full_path not in self.csv_lst:
                self.csv_lst.append(child_full_path)

            # if it's directory call the function again
            child_item.setCheckState(0, Qt.Checked)
            self.dir_checked(child_item)

    def dir_unchecked(self, item):
        """The function remove the unchecked directory and its children from the corresponding lists
        (dir_list and csvLst) and recursively checks all child items under the directory"""
        # get item's full path
        item_path = self.get_full_path_for_tree_item(item)

        # check if item path unchecked is dir and if it's in dir_list
        if os.path.isdir(item_path) and item_path in self.dir_list:
            # remove directory path from dir_list
            self.dir_list.remove(item_path)

        # loop on item's children recursively
        for i in range(item.childCount()):
            child_item = item.child(i)
            # get full path of child
            child_full_path = self.get_full_path_for_tree_item(child_item)

            # if the child is file then remove it from csv list
            if os.path.isfile(child_full_path) and child_full_path in self.csv_lst:
                self.csv_lst.remove(child_full_path)

            # if it's directory call the function again
            child_item.setCheckState(0, Qt.Unchecked)
            self.dir_unchecked(child_item)

    def on_rejected(self):
        """The function resets the state of the dialog and clears any selected values
         or lists associated with it when the user cancels the dialog."""
        # Perform actions when the dialog is rejected (Cancel button clicked)
        # clear tree every time you run the plugin
        self.dlg.csv_tree.clear()
        self.dlg.rootDirLineEdit.clear()
        self.y_field = self.dlg.yfield_cmbBox.clear()
        self.x_field = self.dlg.xfield_cmbBox.clear()
        self.dlg.crs_cmbBox.clear()
        self.csv_lst = []
        self.dir_list = []
        self.dlg.close()

    def run(self):
        """Run method that performs all the real work"""

        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the plugin is started
        if self.first_start == True:
            self.first_start = False

            self.dlg = CsvLayersListDialog()
            self.dlg.browse_btn.clicked.connect(self.evt_browse_btn_clicked)
            self.dlg.crs_btn.clicked.connect(self.evt_crs_btn_clicked)
            self.dlg.csv_tree.itemClicked.connect(self.evt_itm_selected)
            self.dlg.run_btn.clicked.connect(self.evt_run_btn_clicked)
            self.dlg.rejected.connect(self.on_rejected)
            self.dlg.csv_tree.setHeaderLabels(['CSV Files Tree'])
            self.dlg.csv_tree.header().setDefaultAlignment(Qt.AlignCenter | Qt.AlignVCenter)

        # clear crs combo box every time we run plugin
        self.dlg.crs_cmbBox.clear()

        # clear all warning messages every time we run plugin
        self.iface.messageBar().clearWidgets()

        # get recent CRS authority identifier in list
        self.recent_crs_lst = QSettings().value('UI/recentProjectionsAuthId')
        # QSettings().remove('UI/recentProjections')
        # QSettings().remove('UI/recentProjectionsAuthId')

        # check if there's any recent CRS
        if self.recent_crs_lst:
            # get default CRS authid & description
            default_crs_authid = QgsProject.instance().crs().authid()
            default_crs_description = QgsProject.instance().crs().description()
            # concatenate both default authid & description then add them as item in combocox list
            self.dlg.crs_cmbBox.addItem(default_crs_authid + ' - ' + default_crs_description)
            # set it as current item displayed initially in combox
            self.dlg.crs_cmbBox.setCurrentText(default_crs_authid + ' - ' + default_crs_description)

            # loop on CRS list and get description for each then add both to combo box
            for crs_authid in self.recent_crs_lst:
                # use authority identifier to get description
                crs_description = QgsCoordinateReferenceSystem(crs_authid).description()
                # concatenate both authid & description then add them as item in combocox list
                self.dlg.crs_cmbBox.addItem(crs_authid + ' - ' + crs_description)
        # if there's no recent CRS
        else:
            # get default CRS authid & description
            default_crs_authid = QgsProject.instance().crs().authid()
            default_crs_description = QgsProject.instance().crs().description()
            # concatenate both default authid & description then add them as item in combocox list
            self.dlg.crs_cmbBox.addItem(default_crs_authid + ' - ' + default_crs_description)

        # show the dialog
        self.dlg.show()
