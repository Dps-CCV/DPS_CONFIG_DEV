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


class NukeSceneOperations(HookBaseClass):
    """
    Hook to handle Nuke scene operations and event registration.

    This hook registers Nuke callbacks to automatically refresh validation
    when the scene changes (nodes created/deleted/modified).
    """

    def __init__(self, *args, **kwargs):
        super(NukeSceneOperations, self).__init__(*args, **kwargs)

        # Store callback references
        self._reset_callback = None
        self._change_callback = None

        # Track callback IDs for cleanup
        self._on_create_callbacks = []
        self._on_destroy_callbacks = []
        self._on_script_load_callbacks = []
        self._on_script_save_callbacks = []

    def register_scene_events(self, reset_callback, change_callback):
        """
        Register events for when the scene has changed.

        :param reset_callback: Callback function to reset the Data Validation App.
        :type reset_callback: callable
        :param change_callback: Callback function to handle changes to the scene.
        :type change_callback: callable
        """

        self.logger.debug("Registering Nuke scene event callbacks")

        # Store callbacks
        self._reset_callback = reset_callback
        self._change_callback = change_callback

        # Register Nuke callbacks for node deletion
        # This will trigger when nodes are deleted (e.g., from delete_one action)
        try:
            # OnDestroy: Triggers when nodes are deleted
            nuke.addOnDestroy(
                self._on_node_destroyed,
                nodeClass='*'
            )
            self.logger.debug("  Registered onDestroy callback")

            # OnCreate: Triggers when nodes are created (optional)
            nuke.addOnCreate(
                self._on_node_created,
                nodeClass='*'
            )
            self.logger.debug("  Registered onCreate callback")

            # OnScriptLoad: Reset validation when new script is loaded
            nuke.addOnScriptLoad(
                self._on_script_loaded
            )
            self.logger.debug("  Registered onScriptLoad callback")

            # OnScriptSave: Optional - mark as changed when script is saved
            nuke.addOnScriptSave(
                self._on_script_saved
            )
            self.logger.debug("  Registered onScriptSave callback")

            self.logger.info("Nuke scene event callbacks registered successfully")

        except Exception as e:
            self.logger.error("Failed to register Nuke callbacks: %s" % str(e))

    def unregister_scene_events(self):
        """
        Unregister the scene events.

        Cleans up callback references when the Data Validation App is closed.
        """

        self.logger.debug("Unregistering Nuke scene event callbacks")

        # Clear callback references
        self._reset_callback = None
        self._change_callback = None

        # Note: Nuke's API doesn't provide removeOnCreate/removeOnDestroy methods
        # The callbacks will remain but won't do anything since we've cleared the references

        self.logger.info("Nuke scene event callbacks unregistered")

    def _on_node_destroyed(self):
        """
        Callback triggered when a node is destroyed.

        This will call reset_callback to refresh the validation UI.
        """

        # Don't trigger during undo/redo operations
        if self._is_undo_redo_in_progress():
            return

        # Call reset callback to refresh validation
        if self._reset_callback:
            try:
                self.logger.debug("Node destroyed - triggering validation reset")
                self._reset_callback()
            except Exception as e:
                self.logger.error("Error in reset callback: %s" % str(e))

    def _on_node_created(self):
        """
        Callback triggered when a node is created.

        This will call change_callback to show a warning that validation may be stale.
        """

        # Don't trigger during undo/redo operations
        if self._is_undo_redo_in_progress():
            return

        # Call change callback to show warning
        if self._change_callback:
            try:
                self.logger.debug("Node created - triggering validation change warning")
                self._change_callback()
            except Exception as e:
                self.logger.error("Error in change callback: %s" % str(e))

    def _on_script_loaded(self):
        """
        Callback triggered when a script is loaded.

        Resets validation for the new scene.
        """

        if self._reset_callback:
            try:
                self.logger.debug("Script loaded - resetting validation")
                self._reset_callback()
            except Exception as e:
                self.logger.error("Error in reset callback: %s" % str(e))

    def _on_script_saved(self):
        """
        Callback triggered when a script is saved.

        Optionally mark validation as potentially changed.
        """

        # Usually we don't need to refresh on save
        # Uncomment if you want to show change warning on save
        # if self._change_callback:
        #     self._change_callback()
        pass

    def _is_undo_redo_in_progress(self):
        """
        Check if an undo/redo operation is in progress.

        :return: True if undo/redo is in progress, False otherwise
        """
        try:
            # Nuke doesn't have a direct API for this
            # This is a workaround - may not work in all versions
            return False  # TODO: Find a reliable way to detect undo/redo
        except:
            return False