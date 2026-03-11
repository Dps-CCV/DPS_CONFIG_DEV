# Copyright (c) 2024 Autodesk Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the ShotGrid Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the ShotGrid Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Autodesk Inc.

import os

import sgtk
import nuke
import reportUnusedNodes
import reportBboxNodes


HookBaseClass = sgtk.get_hook_baseclass()


class NukeDataValidationHook(HookBaseClass):
    """
    Hook to define Alias scene validation functionality.
    """


    def sanitize_check_result(self, errors):
        """ "
        Sanitize the value returned by any validate function to conform to the standard format.

        This method must be implemented by the subclass.

        Each engine will provide their own validation functions which should return the list of
        objects that do not follow the validation rule. These objects will be referred to as
        "errors". In order for the Data Validation App to handle these objects coming from
        different DCCs, the error objects need to be sanitized into a format that the Data
        Validation App can handle. The standard format that the Data Validation App excepts
        is a list of dictionaries, where each dictionary defines a DCC error object with
        the following keys:

            :is_valid: ``bool`` True if the validate function succeed with the current data, else False.
            :errors: ``List[dict]`` The list of error objects (found by the validate function). None or empty list if the current data is valid. List elements have the following keys:

                :id: ``str | int`` A unique identifier for the error object.
                :name: ``str`` The display name for the error object.
                :type: ``str`` The display name of the error object type (optional).

        This method will be called by the Data Validation App after any validate function is
        called, in order to receive the validate result in the required format.

        :param errors: The value returned by a validate function that needs to be sanitized to
            the standard format.
        :type errors: any

        :return: The validation result in the standardized format.
        :rtype: dict
        """

        formatted_errors = []

        for err in errors:
            formatted_errors.append({"id": err, "name": err.name()})

        return {"is_valid": not errors, "errors": formatted_errors}

    def get_validation_data(self):
        """
        Return the validation rule data set to validate an Alias scene.
        This method will retrieve the default validation rules returned by
        :meth:`AliasSceneDataValidator.get_validation_data`. To customize the default
        validation rules, override this hook method to modify the returned data dictionary.
        The dictionary returned by this function should be formated such that it can be passed
        to the :class:`~tk-multi-data-validation:api.data.ValidationRule` class constructor to
        create a new validation rule object.
        :return: The validation rules data set.
        :rtype: dict
        """

        check_list = {
            "various_writes": {
                "name": "More than one write render",
                "description": """Check: write Render 16bits nodes<br/>
                            """,
                "error_msg": "Found more than one Render 16bit write",
                "check_func": self.check_write_nodes,
                "actions": [
                    {"name": "Select All", "callback": self.select_all_items},
                ],
                "item_actions": [
                    {
                        "name": "Select",
                        "callback": self.select_one,
                    },
                ],
            },
            "unused_nodes": {
                "name": "Delete Unused Nodes",
                "description": """Check: Unused nodes<br/>
                                Fix: Delete""",
                "error_msg": "Found unused nodes",
                "check_func": self.check_unused_nodes,
                "fix_func": self.fix_unused_nodes,
                "fix_name": "Delete All unused nodes",
                "fix_tooltip": "Delete Unused Nodes.",
                "actions": [
                    {"name": "Select All", "callback": self.select_all_items},
                ],
                "item_actions": [
                    {
                        "name": "Select",
                        "callback": self.select_one,
                    },
                    {
                        "name": "Delete",
                        "callback": self.delete_one,
                    },
                ],
            },
            "bbox_nodes": {
                "name": "Nodes with Big Bbox",
                "description": """Check: bbox<br/>
                            """,
                "error_msg": "Found large bbox nodes",
                "check_func": self.check_bbox,
                "actions": [
                    {"name": "Select All", "callback": self.select_all_items},
                ],
                "item_actions": [
                    {
                        "name": "Select",
                        "callback": self.select_one,
                    },
                ],
            },
            "check_output_channels": {
                "name": "Check output channels",
                "description": """Check: channels<br/>
                        """,
                "error_msg": "Output tree has more than rgba channels",
                "check_func": self.check_channels,
                "actions": [
                    {"name": "Select All", "callback": self.select_all_items},
                ],
                "item_actions": [
                    {
                        "name": "Select",
                        "callback": self.select_one,
                    },
                ],
            },
            "check_material": {
                "name": "Check material outside of the project",
                "description": """Check: sorce material<br/>
                    """,
                "error_msg": "Some material its outside of the project",
                "check_func": self.check_materials,
                "actions": [
                    {"name": "Select All", "callback": self.select_all_items},
                ],
                "item_actions": [
                    {
                        "name": "Select",
                        "callback": self.select_one,
                    },
                ],
            },
            "check_colorspace": {
                "name": "Check colorspace settings",
                "description": """Check: colorspace<br/>
                    """,
                "error_msg": "Some nodes have different colorspace settings than the project",
                "check_func": self.check_colorspaces,
                "actions": [
                    {"name": "Select All", "callback": self.select_all_items},
                ],
                "item_actions": [
                    {
                        "name": "Select",
                        "callback": self.select_one,
                    },
                ],
            },
            "check_camera_trackers": {
                "name": "Check camera trackers",
                "description": """Check: camera trackers<br/>
                """,
                "error_msg": "There are more than two camera trackers. That could be slowing down the script",
                "check_func": self.check_camera_trackers,
                "actions": [
                    {"name": "Select All", "callback": self.select_all_items},
                ],
                "item_actions": [
                    {
                        "name": "Select",
                        "callback": self.select_one,
                    },
                ],
            },
        }
        return check_list

    # Check methods
    # ---------------------------------------------------------------------------

    def check_write_nodes(self):
        """Check if there are more than one Write Render 16bits nodes in the current Nuke session."""
        renderNodes = []
        for node in nuke.allNodes('WriteTank'):
            if node.knob('tk_profile_list').value() == 'Render 16bit':
                renderNodes.append(node)
        return renderNodes


    def check_materials(self):
        materialNodes = []
        for a in nuke.allNodes('Read'):
            if a.knob('file').evaluate() != None and os.environ['PROJECT_PATH'] not in a.knob('file').evaluate():
                materialNodes.append(a)
        for a in nuke.allNodes('Camera2'):
            if a.knob('file').evaluate() != None and os.environ['PROJECT_PATH'] not in a.knob('file').evaluate() and a.knob(
                    'read_from_file').value() == 1:
                materialNodes.append(a)
        for a in nuke.allNodes('Camera4'):
            if a.knob('import_enabled').value() == 1 and a.knob('file').evaluate() != None and os.environ[
                'PROJECT_PATH'] not in a.knob('file').evaluate():
                materialNodes.append(a)
        for a in nuke.allNodes('ReadGeo2'):
            if a.knob('file').evaluate() != None and os.environ['PROJECT_PATH'] not in a.knob('file').evaluate():
                materialNodes.append(a)
        for a in nuke.allNodes('ReadGeo'):
            if a.knob('file').evaluate() != None and os.environ['PROJECT_PATH'] not in a.knob('file').evaluate():
                materialNodes.append(a)
        for a in nuke.allNodes('DeepRead'):
            if a.knob('file').evaluate() != None and os.environ['PROJECT_PATH'] not in a.knob('file').evaluate():
                materialNodes.append(a)
        return materialNodes

    def check_colorspaces(self):
        x = nuke.allNodes("Read")
        nodeErrors = []
        for a in x:
            if '_LGT_' in a.knob('file').evaluate() and 'AcesCg' not in a.knob('colorspace').value():
                nodeErrors.append(a)
            if '_PARAFX_' in a.knob('file').evaluate() and os.environ['PROJECTCOLORSPACE'] not in a.knob(
                    'colorspace').value():
                nodeErrors.append(a)
        e = nuke.allNodes('WriteTank')
        for b in e:
            if b.knob('tk_profile_list').value() == 'Render 16bits' and os.environ['PROJECTCOLORSPACE'] not in b.knob(
                    'colorspace').value():
                nodeErrors.append(b)
        if 'AcesCg' not in nuke.root().knob('workingSpaceLUT').value():
            nodeErrors.append(nuke.root())
        return nodeErrors

    def check_camera_trackers(self):
        if len(nuke.allNodes('CameraTracker'))>2:
            return nuke.allNodes('CameraTracker')
        else:
            return []

    def check_unused_nodes(self):
        """Check if there are unknown nodes in the current Nuke session."""

        return reportUnusedNodes.analyze()

    def check_bbox(self):
        """Check large bbox nodes."""

        return reportBboxNodes.returnBboxNodes()


    def check_channels(self, profile_name="Render 16bits"):
        """
        Deselects all nodes, then selects every node that has a 'tk_profile' knob (i.e. WriteTank gizmos)
        where:
          - tk_profile == profile_name
          - the node's input(0) has any channels beyond the 'rgba' layer (e.g., depth.Z, motion, normals, etc.)

        Returns:
            list[str]: names of matching nodes (which are also selected in the DAG).
        """
        # Deselect everything first
        for n in nuke.allNodes(recurseGroups=True):
            try:
                n['selected'].setValue(False)
            except Exception:
                pass

        matches = []

        # Look through all nodes (including inside Groups)
        for node in nuke.allNodes('WriteTank'):
            tk_knob = node.knob('tk_profile_list')
            if not tk_knob:
                continue  # not a WriteTank-style node

            # Check profile
            try:
                if tk_knob.value() != profile_name:
                    continue
            except Exception:
                continue

            # Get the input to the WriteTank node
            inp = node.input(0)
            if inp is None:
                continue

            # Inspect the channels available at the input
            try:
                chs = inp.channels()  # e.g., ['rgba.red','rgba.green','rgba.blue','rgba.alpha','depth.Z', ...]
            except Exception:
                # Can't evaluate channels here; skip this node
                continue

            # Determine if there are any non-rgba layers present
            has_channels_beyond_rgba = any(ch.split('.')[0] != 'rgba' for ch in chs)

            if has_channels_beyond_rgba:
                try:
                    node['selected'].setValue(True)
                except Exception:
                    pass
                matches.append(node.name())

        return matches


    # ---------------------------------------------------------------------------
    # Fix and actions methods
    # ---------------------------------------------------------------------------

    def fix_unused_nodes(self, errors):
        undo = nuke.Undo()
        undo.begin()
        for item in errors:
            a = nuke.toNode(item['name'])
            nuke.delete(a)
        undo.end()

    def select_all_items(self, errors):
        """Select a list of items."""
        # clear the previous selection before selecting the items
        for node in nuke.allNodes():
            node.knob('selected').setValue(False)
        for item in errors:
            a = nuke.toNode(item['name'])
            a.knob('selected').setValue(True)
        return False

    def select_one(self, errors):
        item = errors[0]
        # clear the previous selection before selecting the items
        for node in nuke.allNodes():
            node.knob('selected').setValue(False)

        item.knob('selected').setValue(True)
        nuke.zoom(3, [item.xpos(), item.ypos()])
        return False

    def delete_one(self, errors, rule_name=None):
        undo = nuke.Undo()
        undo.begin()
        item = errors[0]
        nuke.delete(item)
        undo.end()
        return item


    # ---------------------------------------------------------------------------
    # Utilities
    # ---------------------------------------------------------------------------



