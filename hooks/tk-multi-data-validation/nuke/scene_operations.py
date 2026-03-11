# Copyright (c) 2024 Autodesk Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the ShotGrid Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the ShotGrid Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Autodesk Inc.

import sgtk
import nuke

HookBaseClass = sgtk.get_hook_baseclass()


class NukeSceneOperationsHook(HookBaseClass):
    """Hook class that sets up Nuke events to update the Data Validation App."""

    def __init__(self, *args, **kwargs):
        super(NukeSceneOperationsHook, self).__init__(*args, **kwargs)
        self.__reset_callback = None
        self.__change_callback = None
        self.__callbacks_registered = False

    def register_scene_events(self, reset_callback, change_callback):
        """
        Register events for when the scene has changed.

        The function reset_callback provided will reset the current Data Validation App,
        when called. The function change_callback provided will display a warning in the
        Data Validation App UI that the scene has changed and the current validation state
        may be stale.

        :param reset_callback: Callback function to reset the Data Validation App.
        :type reset_callback: callable
        :param change_callback: Callback function to handle the changes to the scene.
        :type change_callback: callable
        """

        if self.__callbacks_registered:
            return  # Scene events already registered

        # Store callbacks
        self.__reset_callback = reset_callback
        self.__change_callback = change_callback

        # Register Nuke scene events
        nuke.addOnScriptLoad(self._on_script_loaded)
        nuke.addOnScriptSave(self._on_script_saved)
        nuke.addOnScriptClose(self._on_script_closed)

        # Register Nuke node events
        nuke.addOnCreate(self._on_node_created, nodeClass='*')
        nuke.addOnDestroy(self._on_node_removed, nodeClass='*')

        self.__callbacks_registered = True

    def unregister_scene_events(self):
        """
        Unregister the scene events.

        Note: Nuke doesn't provide removeOnCreate/removeOnDestroy methods,
        so we clear the callback references to prevent them from being called.
        """

        self.__reset_callback = None
        self.__change_callback = None
        self.__callbacks_registered = False

    # Scene event callbacks
    # -------------------------------------------------------------------------

    def _on_script_loaded(self):
        """Callback when a script is loaded."""
        if self.__reset_callback:
            self.__reset_callback()

    def _on_script_saved(self):
        """Callback when a script is saved."""
        # Optionally show change warning on save
        # Usually not needed as save doesn't affect validation
        pass

    def _on_script_closed(self):
        """Callback when a script is closed."""
        if self.__reset_callback:
            self.__reset_callback()

    # Node event callbacks
    # -------------------------------------------------------------------------

    def _on_node_created(self):
        """Callback when a node is created."""
        if self.__change_callback:
            self.__change_callback(text="Node added")

    def _on_node_removed(self):
        """Callback when a node is removed."""
        if self.__change_callback:
            self.__change_callback(text="Node removed")