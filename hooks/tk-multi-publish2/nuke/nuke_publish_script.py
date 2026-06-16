# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import os
import nuke
import sgtk
from sgtk.util.filesystem import ensure_folder_exists
import WrapItUpLogger_v2
import shutil


HookBaseClass = sgtk.get_hook_baseclass()


class NukeSessionPublishPlugin(HookBaseClass):
    """
    Plugin for publishing an open nuke session.

    This hook relies on functionality found in the base file publisher hook in
    the publish2 app and should inherit from it in the configuration. The hook
    setting for this plugin should look something like this::

        hook: "{self}/publish_file.py:{engine}/tk-multi-publish2/basic/nuke_publish_script.py"

    """

    # NOTE: The plugin icon and name are defined by the base file plugin.

    @property
    def description(self):
        """
        Verbose, multi-line description of what the plugin does. This can
        contain simple html for formatting.
        """

        loader_url = "https://support.shotgunsoftware.com/hc/en-us/articles/219033078"

        return """
        Publishes the file to Shotgun. A <b>Publish</b> entry will be
        created in Shotgun which will include a reference to the file's current
        path on disk. If a publish template is configured, a copy of the
        current session will be copied to the publish template path which
        will be the file that is published. Other users will be able to access
        the published file via the <b><a href='%s'>Loader</a></b> so long as
        they have access to the file's location on disk.

        If the session has not been saved, validation will fail and a button
        will be provided in the logging output to save the file.

        <h3>File versioning</h3>
        If the filename contains a version number, the process will bump the
        file to the next version after publishing.

        The <code>version</code> field of the resulting <b>Publish</b> in
        Shotgun will also reflect the version number identified in the filename.
        The basic worklfow recognizes the following version formats by default:

        <ul>
        <li><code>filename.v###.ext</code></li>
        <li><code>filename_v###.ext</code></li>
        <li><code>filename-v###.ext</code></li>
        </ul>

        After publishing, if a version number is detected in the work file, the
        work file will automatically be saved to the next incremental version
        number. For example, <code>filename.v001.ext</code> will be published
        and copied to <code>filename.v002.ext</code>

        If the next incremental version of the file already exists on disk, the
        validation step will produce a warning, and a button will be provided in
        the logging output which will allow saving the session to the next
        available version number prior to publishing.

        <br><br><i>NOTE: any amount of version number padding is supported. for
        non-template based workflows.</i>

        <h3>Overwriting an existing publish</h3>
        In non-template workflows, a file can be published multiple times,
        however only the most recent publish will be available to other users.
        Warnings will be provided during validation if there are previous
        publishes.
        """ % (
            loader_url,
        )

    @property
    def settings(self):
        """
        Dictionary defining the settings that this plugin expects to receive
        through the settings parameter in the accept, validate, publish and
        finalize methods.

        A dictionary on the following form::

            {
                "Settings Name": {
                    "type": "settings_type",
                    "default": "default_value",
                    "description": "One line description of the setting"
            }

        The type string should be one of the data types that toolkit accepts as
        part of its environment configuration.
        """

        # inherit the settings from the base publish plugin
        base_settings = super(NukeSessionPublishPlugin, self).settings or {}

        # settings specific to this class
        nuke_publish_settings = {
            "Publish Template": {
                "type": "template",
                "default": None,
                "description": "Template path for published work files. Should"
                "correspond to a template defined in "
                "templates.yml.",
            }
        }

        # update the base settings
        base_settings.update(nuke_publish_settings)

        return base_settings

    @property
    def item_filters(self):
        """
        List of item types that this plugin is interested in.

        Only items matching entries in this list will be presented to the
        accept() method. Strings can contain glob patters such as *, for example
        ["maya.*", "file.maya"]
        """
        return ["nuke.session"]

    def accept(self, settings, item):
        """
        Method called by the publisher to determine if an item is of any
        interest to this plugin. Only items matching the filters defined via the
        item_filters property will be presented to this method.

        A publish task will be generated for each item accepted here. Returns a
        dictionary with the following booleans:

            - accepted: Indicates if the plugin is interested in this value at
                all. Required.
            - enabled: If True, the plugin will be enabled in the UI, otherwise
                it will be disabled. Optional, True by default.
            - visible: If True, the plugin will be visible in the UI, otherwise
                it will be hidden. Optional, True by default.
            - checked: If True, the plugin will be checked in the UI, otherwise
                it will be unchecked. Optional, True by default.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process

        :returns: dictionary with boolean keys accepted, required and enabled
        """

        # if a publish template is configured, disable context change. This
        # is a temporary measure until the publisher handles context switching
        # natively.
        if settings.get("Publish Template").value:
            item.context_change_allowed = False

        path = _session_path()

        if not path:
            # the session has not been saved before (no path determined).
            # provide a save button. the session will need to be saved before
            # validation will succeed.
            self.logger.warn(
                "The Nuke script has not been saved.", extra=_get_save_as_action()
            )

        self.logger.info(
            "Nuke '%s' plugin accepted the current Nuke script." % (self.name,)
        )
        return {"accepted": True, "checked": True}

    def validate(self, settings, item):
        """
        Validates the given item to check that it is ok to publish. Returns a
        boolean to indicate validity.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        :returns: True if item is valid, False otherwise.
        """

        # this method will handle validation specific to the nuke script itself.
        # the base class plugin will handle validation of the file itself

        publisher = self.parent
        path = _session_path()

        # ---- ensure the session has been saved

        if not path:
            # the session still requires saving. provide a save button.
            # validation fails.
            error_msg = "The Nuke script has not been saved."
            self.logger.error(error_msg, extra=_get_save_as_action())
            raise Exception(error_msg)

        # ---- check the session against any attached work template

        # get the path in a normalized state. no trailing separator,
        # separators are appropriate for current os, no double separators,
        # etc.
        path = sgtk.util.ShotgunPath.normalize(path)

        # if the session item has a known work template, see if the path
        # matches. if not, warn the user and provide a way to save the file to
        # a different path
        work_template = item.properties.get("work_template")
        if work_template:
            if not work_template.validate(path):
                self.logger.warning(
                    "The current session does not match the configured work "
                    "template.",
                    extra={
                        "action_button": {
                            "label": "Save File",
                            "tooltip": "Save the current Nuke session to a "
                            "different file name",
                            # will launch wf2 if configured
                            "callback": _get_save_as_action(),
                        }
                    },
                )
            else:
                self.logger.debug("Work template configured and matches session file.")
        else:
            self.logger.debug("No work template configured.")

        # ---- see if the version can be bumped post-publish

        # check to see if the next version of the work file already exists on
        # disk. if so, warn the user and provide the ability to save to the next
        # available version now
        (next_version_path, version) = self._get_next_version_info(path, item)
        if next_version_path and os.path.exists(next_version_path):

            # determine the next available version_number. just keep asking for
            # the next one until we get one that doesn't exist.
            while os.path.exists(next_version_path):
                (next_version_path, version) = self._get_next_version_info(
                    next_version_path, item
                )

            error_msg = "The next version of this file already exists on disk."
            self.logger.error(
                error_msg,
                extra={
                    "action_button": {
                        "label": "Save to v%s" % (version,),
                        "tooltip": "Save to the next available version number, "
                        "v%s" % (version,),
                        "callback": lambda: _save_session(next_version_path),
                    }
                },
            )
            raise Exception(error_msg)

        # ---- populate the necessary properties and call base class validation

        # populate the publish template on the item if found
        publish_template_setting = settings.get("Publish Template")
        publish_template = publisher.engine.get_template_by_name(
            publish_template_setting.value
        )
        if publish_template:
            item.properties["publish_template"] = publish_template

        # set the session path on the item for use by the base plugin validation
        # step. NOTE: this path could change prior to the publish phase.
        item.properties["path"] = path

        # run the base class validation
        return super(NukeSessionPublishPlugin, self).validate(settings, item)

    def publish(self, settings, item):
        """
        Executes the publish logic for the given item and settings.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        # get the path in a normalized state. no trailing separator, separators
        # are appropriate for current os, no double separators, etc.
        path = sgtk.util.ShotgunPath.normalize(_session_path())

        # ensure the session is saved
        _save_session(path)

        # update the item with the saved session path
        item.properties["path"] = path

        # add dependencies for the base class to register when publishing
        item.properties[
            "publish_dependencies"
        ] = _nuke_find_additional_script_dependencies()

        # let the base class register the publish
        super(NukeSessionPublishPlugin, self).publish(settings, item)
        publish_data = item.get_property("sg_publish_data")
        item.properties["parched_type"] = publish_data['type']
        item.properties["parched_id"] = publish_data['id']

    def finalize(self, settings, item):
        """
        Execute the finalization pass. This pass executes once all the publish
        tasks have completed, and can for example be used to version up files.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        # do the base class finalization
        super(NukeSessionPublishPlugin, self).finalize(settings, item)

        # EFECTOSCOPIO ARCHIVING
        scriptPath = os.path.normpath(nuke.root().name())
        base = os.path.basename(nuke.root().name()).split(".")[0]
        if 'SHOT_FOLDER' in os.environ.keys():
            ShotFolder = os.path.join(*os.environ['SHOT_FOLDER'].split(os.sep)[3:])
            archivePath = os.path.normpath(os.path.join(os.environ['PROJECT_PATH'], 'ARCHIVE', ShotFolder, base))[:-5]
        elif 'ASSET_FOLDER' in os.environ.keys():
            AssetFolder = os.path.join(*os.environ['ASSET_FOLDER'].split(os.sep)[3:])
            archivePath = os.path.normpath(os.path.join(os.environ['PROJECT_PATH'], 'ARCHIVE', AssetFolder, base))[:-5]

        try:
            self.logger.info("Starting Archive of the script. Be patient my friend")

            if os.path.exists(archivePath):
                # step 1: clean up .nk scripts so they get regenerated
                _cleanup_archive_scripts(archivePath, self.logger)
            else:
                os.makedirs(archivePath)

            # step 2: dry run to find out what WrapItUp intends to archive
            import WrapItUpLogger as WIU
            WIU.WrapItUp_v2(
                nk=scriptPath,
                out=archivePath,
                parentdircount=3,
                startnow=False,  # <-- preview only, no copying
                fonts=True,
                licinteractive=True,
                relativerelinked=True,
                gizmos=True,
                logger=self.logger
            )

            # step 3: reconcile — remove stale files no longer in the script
            intended_paths = _get_intended_archive_paths(WIU.WIU_SilentList, archivePath)
            _reconcile_archive_media(archivePath, intended_paths, self.logger)

            # step 4: actual archive run (smart symlink skipping handles the rest)
            WIU.WrapItUp_v2(
                nk=scriptPath,
                out=archivePath,
                parentdircount=3,
                startnow=True,  # <-- now actually copy/link
                fonts=True,
                licinteractive=True,
                relativerelinked=True,
                gizmos=True,
                logger=self.logger
            )

            type = item.get_property("parched_type")
            id = item.get_property("parched_id")
            if type is not None and id is not None:
                self.sgtk.shotgun.update(type, id, {"sg_archived": True})

            self.logger.info("Scene archived successfully")
        except:
            self.logger.warning("Archive was not possible")


        # bump the session file to the next version
        self._save_to_next_version(item.properties["path"], item, _save_session)


def _nuke_find_additional_script_dependencies():
    """
    Find all dependencies for the current nuke script
    """

    # figure out all the inputs to the scene and pass them as dependency
    # candidates
    dependency_paths = []
    for read_node in nuke.allNodes("Read"):
        # make sure we have a file path and normalize it
        # file knobs set to "" in Python will evaluate to None. This is
        # different than if you set file to an empty string in the UI, which
        # will evaluate to ""!
        file_path = read_node.knob("file").evaluate()
        if not file_path:
            continue
        file_path = sgtk.util.ShotgunPath.normalize(file_path)
        if file_path not in dependency_paths:
            dependency_paths.append(file_path)
    for readgeo_node in nuke.allNodes("ReadGeo2"):
        # make sure we have a file path and normalize it
        # file knobs set to "" in Python will evaluate to None. This is
        # different than if you set file to an empty string in the UI, which
        # will evaluate to ""!
        file_path = readgeo_node.knob("file").evaluate()
        if not file_path:
            continue
        file_path = sgtk.util.ShotgunPath.normalize(file_path)
        if file_path not in dependency_paths:
            dependency_paths.append(file_path)
    for cam_node in nuke.allNodes("Camera2"):
        # make sure we have a file path and normalize it
        # file knobs set to "" in Python will evaluate to None. This is
        # different than if you set file to an empty string in the UI, which
        # will evaluate to ""!
        file_path = cam_node.knob("file").evaluate()
        if not file_path:
            continue
        file_path = sgtk.util.ShotgunPath.normalize(file_path)
        if file_path not in dependency_paths:
            dependency_paths.append(file_path)

    return dependency_paths


def _save_session(path):
    """
    Save the current session to the supplied path.
    """
    # Nuke won't ensure that the folder is created when saving, so we must make sure it exists
    ensure_folder_exists(os.path.dirname(path))

    nuke.scriptSaveAs(path, True)


def _session_path():
    """
    Return the path to the current session
    :return:
    """
    root_name = nuke.root().name()
    return None if root_name == "Root" else root_name


def _get_save_as_action():
    """
    Simple helper for returning a log action dict for saving the session
    """

    engine = sgtk.platform.current_engine()

    # default save callback
    callback = nuke.scriptSaveAs

    # if workfiles2 is configured, use that for file save
    if "tk-multi-workfiles2" in engine.apps:
        app = engine.apps["tk-multi-workfiles2"]
        if hasattr(app, "show_file_save_dlg"):
            callback = app.show_file_save_dlg

    return {
        "action_button": {
            "label": "Save As...",
            "tooltip": "Save the current session",
            "callback": callback,
        }
    }
def _cleanup_archive_scripts(archive_path, logger):
    """
    Selectively clean the archive folder before a re-publish.
    Removes only .nk scripts, log files and gizmo init files
    so they get regenerated fresh.
    Media symlinks are left in place to be reused if unchanged.
    """
    import glob

    patterns_to_delete = [
        # nuke scripts at root level
        os.path.join(archive_path, '*.nk'),
        # log
        os.path.join(archive_path, 'log.csv'),
        # temporary relink files
        os.path.join(archive_path, 'WrapItUp_Temp-RELINK_*.py'),
        # gizmo init/menu files (always regenerated)
        os.path.join(archive_path, 'GIZMOS', 'init.py'),
        os.path.join(archive_path, 'GIZMOS', 'menu.py'),
        os.path.join(archive_path, 'GIZMOS', 'Collected', '*', 'init.py'),
        os.path.join(archive_path, 'GIZMOS', 'Collected', '*', 'menu.py'),
    ]

    for pattern in patterns_to_delete:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
                logger.info("Removed for regeneration: %s" % f)
            except Exception as e:
                logger.warning("Could not remove %s: %s" % (f, str(e)))

def _reconcile_archive_media(archive_path, intended_files, logger):
    """
    Remove symlinks from the archive that are no longer part of the current
    publish. Compares existing symlinks in MEDIA/PROJECT_DIRECTORY folders
    against the list of files WrapItUp intends to place there.

    :param archive_path:    Root of the archive folder
    :param intended_files:  Set of normalised absolute paths that SHOULD be
                            in the archive after this publish
    :param logger:          sgtk logger
    """
    import stat

    media_roots = [
        os.path.join(archive_path, 'MEDIA'),
        os.path.join(archive_path, 'PROJECT_DIRECTORY'),
        os.path.join(archive_path, 'FONTS'),
        os.path.join(archive_path, 'GIZMOS', 'Collected'),
    ]

    removed = 0
    for media_root in media_roots:
        if not os.path.isdir(media_root):
            continue

        for dirpath, dirnames, filenames in os.walk(media_root, topdown=False):
            for filename in filenames:
                filepath = os.path.normpath(os.path.join(dirpath, filename))

                if filepath not in intended_files:
                    try:
                        os.remove(filepath)
                        logger.info("Removed stale file from archive: %s" % filepath)
                        removed += 1
                    except Exception as e:
                        logger.warning("Could not remove stale file %s: %s" % (filepath, str(e)))

            # remove empty directories left behind
            try:
                if not os.listdir(dirpath):
                    os.rmdir(dirpath)
            except Exception:
                pass

    logger.info("Reconciliation complete: %d stale file(s) removed." % removed)

def _get_intended_archive_paths(wrap_preview_result, archive_path):
    """
    WrapItUp silent preview returns a list of strings like:
      'nodeName   /original/source/path'
    We need the *destination* paths in the archive, not the sources.
    Since WrapItUp places files under MEDIA/<nodename>/<parentdirs>/filename
    we reconstruct the destination from what's already been built into
    WrapItUp's WIU_PackedPath logic.

    Simpler approach: after a dry run we just collect all files currently
    in the archive that WOULD be written — i.e. we run WrapItUp once with
    startnow=False, then inspect WIU_SilentList which contains [label, index]
    pairs, and use WIU_MediaData to reconstruct destination paths.

    Even simpler: just collect all destination paths by running the copy
    with a custom flag. Since we can't easily hook into WrapItUp internals
    from outside, we instead scan what WOULD exist by checking
    WrapItUp's internal state after the preview call via the returned list.

    Practical approach: parse the label strings from the preview.
    Labels look like: 'nodeName  \t\t/path/to/source/file'
    We extract source paths and resolve their expected archive destinations.
    """
    import WrapItUpLogger as WIU

    intended = set()

    # after _Start(silent, startnow=False) runs, WIU_SilentList is populated
    # with [label_string, data_index] pairs and WIU_MediaData has full info
    # We access these via the module globals
    try:
        for item in WIU.WIU_SilentList:
            data_index = item[1]

            # skip .nk scripts and other non-media items (negative indices)
            if data_index < 0:
                continue

            media_item = WIU.WIU_MediaData[data_index]
            node_name  = _get_node_names_str(media_item[0])
            project_dir = media_item[6]

            # each file in the sequence
            for file_info in media_item[4]:
                source_path = file_info[0]
                # reconstruct destination the same way WrapItUp does
                dest = _reconstruct_wiu_dest(
                    source_path,
                    archive_path,
                    node_name,
                    project_dir,
                    WIU.WIU_NodeNameFolder,
                    WIU.WIU_ParentDirCount
                )
                if dest:
                    intended.add(os.path.normpath(dest))
    except Exception as e:
        pass

    return intended


def _get_node_names_str(node_list):
    names = []
    for n in node_list[:5]:
        try:
            names.append(n.fullName())
        except Exception:
            pass
    return '_'.join(names)


def _reconstruct_wiu_dest(source_path, archive_path, node_name, project_dir, node_name_folder, parent_dir_count):
    """
    Mirrors WrapItUp's PackedPath() logic to reconstruct where a file
    would be placed in the archive.
    """
    try:
        source_path = source_path.replace('\\', '/')
        split = [s for s in source_path.split('/') if s]

        parent_count = min(parent_dir_count, len(split))
        if project_dir:
            parent_count = len(split)

        new_path = (node_name + '/') if (node_name_folder and not project_dir) else ''
        for c in range(parent_count):
            new_path += split[len(split) - (parent_count - c)]
            if c < parent_count - 1:
                new_path += '/'

        # sanitise
        for ch in ':<>$?!;\'\"`*|':
            new_path = new_path.replace(ch, '_')

        subdir = 'PROJECT_DIRECTORY' if project_dir else 'MEDIA'
        return archive_path.replace('\\', '/') + '/' + subdir + '/' + new_path

    except Exception:
        return None