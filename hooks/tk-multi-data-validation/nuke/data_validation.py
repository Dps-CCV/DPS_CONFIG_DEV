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
        }
        return check_list

    # Check methods
    # ---------------------------------------------------------------------------

    def check_unused_nodes(self):
        """Check if there are unknown nodes in the current Maya session."""

        return reportUnusedNodes.analyze()

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

    def delete_one(self, errors):
        undo = nuke.Undo()
        undo.begin()
        item = errors[0]
        nuke.delete(item)
        self.check_unused_nodes()
        undo.end()
        return True
    # ---------------------------------------------------------------------------
    # Utilities
    # ---------------------------------------------------------------------------



