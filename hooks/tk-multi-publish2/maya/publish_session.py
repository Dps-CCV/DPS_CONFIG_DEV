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
import maya.cmds as cmds
import maya.mel as mel
import sgtk
from sgtk.util.filesystem import ensure_folder_exists
from tank_vendor import six
import shutil
import json
from collections import defaultdict



HookBaseClass = sgtk.get_hook_baseclass()


class MayaSessionPublishPlugin(HookBaseClass):
    """
    Plugin for publishing an open maya session.

    This hook relies on functionality found in the base file publisher hook in
    the publish2 app and should inherit from it in the configuration. The hook
    setting for this plugin should look something like this::

        hook: "{self}/publish_file.py:{engine}/tk-multi-publish2/basic/publish_session.py"

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
        base_settings = super(MayaSessionPublishPlugin, self).settings or {}

        # settings specific to this class
        maya_publish_settings = {
            "Publish Template": {
                "type": "template",
                "default": None,
                "description": "Template path for published work files. Should"
                "correspond to a template defined in "
                "templates.yml.",
            },
        }

        # update the base settings
        base_settings.update(maya_publish_settings)

        return base_settings

    @property
    def item_filters(self):
        """
        List of item types that this plugin is interested in.

        Only items matching entries in this list will be presented to the
        accept() method. Strings can contain glob patters such as *, for example
        ["maya.*", "file.maya"]
        """
        return ["maya.session"]

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

        path = item.properties["path"]

        if not path:
            # the session has not been saved before (no path determined).
            # provide a save button. the session will need to be saved before
            # validation will succeed.
            self.logger.warn(
                "The Maya session has not been saved.", extra=_get_save_as_action()
            )

        self.logger.info(
            "Maya '%s' plugin accepted the current Maya session." % (self.name,)
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

        publisher = self.parent
        path =  item.properties["path"]



        # ---- ensure the session has been saved

        if not path:
            # the session still requires saving. provide a save button.
            # validation fails.
            error_msg = "The Maya session has not been saved."
            self.logger.error(error_msg, extra=_get_save_as_action())
            raise Exception(error_msg)

        # ensure we have an updated project root
        project_root = cmds.workspace(q=True, rootDirectory=True)
        item.properties["project_root"] = project_root

        # log if no project root could be determined.
        if not project_root:
            self.logger.info(
                "Your session is not part of a maya project.",
                extra={
                    "action_button": {
                        "label": "Set Project",
                        "tooltip": "Set the maya project",
                        "callback": lambda: mel.eval('setProject ""'),
                    }
                },
            )

        # ---- check the session against any attached work template


        # if the session item has a known work template, see if the path
        # matches. if not, warn the user and provide a way to save the file to
        # a different path
        work_template = item.properties.get("work_template")
        if work_template:
            if not work_template.validate(path):
                self.logger.warning(
                    "The current session does not match the configured work "
                    "file template.",
                    extra={
                        "action_button": {
                            "label": "Save File",
                            "tooltip": "Save the current Maya session to a "
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
        # disk. if so, warn the user and provide the ability to jump to save
        # to that version now
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



        # run the base class validation
        return super(MayaSessionPublishPlugin, self).validate(settings, item)

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
        path = item.properties["path"]

        # ensure the session is saved
        _save_session(path)


        # add dependencies for the base class to register when publishing
        item.properties[
            "publish_dependencies"
        ] = _maya_find_additional_session_dependencies()

        # let the base class register the publish
        super(MayaSessionPublishPlugin, self).publish(settings, item)



        status = {"sg_status_list": "rev"}
        self.parent.sgtk.shotgun.update("Task", item.context.task['id'], status)

    def finalize(self, settings, item):
        """
        Execute the finalization pass. This pass executes once all the publish
        tasks have completed, and can for example be used to version up files.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """
        if item.context.step['name'] in ['LIGHT', 'LIGHT_A', 'RIG_A', 'TEXTURE_A', 'SHADING_A']:
            path = cmds.file(query=True, sn=True)
            file = os.path.basename(path)[:-8]
            base = os.path.basename(path).split(".")[0]
            if 'SHOT_FOLDER' in os.environ.keys():
                ShotFolder = os.path.join(*os.environ['SHOT_FOLDER'].split(os.sep)[3:])
                archivePath = os.path.normpath(os.path.join(os.environ['PROJECT_PATH'], 'ARCHIVE', ShotFolder, base))[:-5]
            elif 'ASSET_FOLDER' in os.environ.keys():
                AssetFolder = os.path.join(*os.environ['ASSET_FOLDER'].split(os.sep)[3:])
                archivePath = os.path.normpath(os.path.join(os.environ['PROJECT_PATH'], 'ARCHIVE', AssetFolder, base))[:-5]
            if os.path.exists(archivePath):
                shutil.rmtree(archivePath)
            os.makedirs(archivePath)
            try:
                result = archive_current_scene(archivePath, file)

                if result:
                    self.logger.info("Scene archived successfully: %s" % result)
                    # Access the published entity created earlier
                    sg_publish = item.get_property("sg_publish_data")

                    if sg_publish:
                        # Update Shotgun/FPT fields as needed
                        self.sgtk.shotgun.update(
                            sg_publish["type"],
                            sg_publish["id"],
                            {"sg_archived": True}  # Any field you want to update
                        )
                else:
                    self.logger.warning("Archive creation returned None - check for errors above")
            except:
                self.logger.warning("Archive was not possible")

        # do the base class finalization
        super(MayaSessionPublishPlugin, self).finalize(settings, item)

        # bump the session file to the next version
        self._save_to_next_version(item.properties["path"], item, _save_session)


    def _copy_work_to_publish(self, settings, item):
        """
        This method handles copying work file path(s) to a designated publish
        location.

        This method requires a "work_template" and a "publish_template" be set
        on the supplied item.

        The method will handle copying the "path" property to the corresponding
        publish location assuming the path corresponds to the "work_template"
        and the fields extracted from the "work_template" are sufficient to
        satisfy the "publish_template".

        The method will not attempt to copy files if any of the above
        requirements are not met. If the requirements are met, the file will
        ensure the publish path folder exists and then copy the file to that
        location.

        If the item has "sequence_paths" set, it will attempt to copy all paths
        assuming they meet the required criteria with respect to the templates.

        """
        # ---- ensure templates are available
        work_template = item.properties.get("work_template")
        if not work_template:
            self.logger.debug(
                "No work template set on the item. "
                "Skipping copy file to publish location."
            )
            return

        publish_template = self.get_publish_template(settings, item)
        if not publish_template:
            self.logger.debug(
                "No publish template set on the item. "
                "Skipping copying file to publish location."
            )
            return


        # by default, the path that was collected for publishing
        work_file = item.properties.path

        # ---- copy the work files to the publish location


        if not work_template.validate(work_file):
            self.logger.warning(
                "Work file '%s' did not match work template '%s'. "
                "Publishing in place." % (work_file, work_template)
            )
            return

        work_fields = work_template.get_fields(work_file)

        missing_keys = publish_template.missing_keys(work_fields)

        if missing_keys:
            self.logger.warning(
                "Work file '%s' missing keys required for the publish "
                "template: %s" % (work_file, missing_keys)
            )
            return

        publish_file = publish_template.apply_fields(work_fields)
        if work_fields["extension"] == "ma":
            typeFile = "mayaAscii"
        else:
            typeFile = "mayaBinary"
        if not os.path.isdir(os.path.dirname(publish_file)):
            os.makedirs(os.path.dirname(publish_file))

        if item.context.step['name'] in ['RIG_A', 'TEXTURE_A', 'SHADING_A']:
            cmds.file(publish_file, exportAll=True, preserveReferences=False, force=True, type=typeFile)
        else:
            cmds.file(publish_file, exportAll=True, preserveReferences=True, force=True, type=typeFile)



        self.logger.debug(
            "Copied work file '%s' to publish file '%s'."
            % (work_file, publish_file)
        )


def _maya_find_additional_session_dependencies():
    """
    Find additional dependencies from the session
    """

    # default implementation looks for references and
    # textures (file nodes) and returns any paths that
    # match a template defined in the configuration
    ref_paths = set()

    # first let's look at maya references
    ref_nodes = cmds.ls(references=True)
    for ref_node in ref_nodes:
        # get the path:
        ref_path = cmds.referenceQuery(ref_node, filename=True)
        # make it platform dependent
        # (maya uses C:/style/paths)
        ref_path = ref_path.replace("/", os.path.sep)
        if ref_path:
            ref_paths.add(ref_path)

    # now look at file texture nodes
    for file_node in cmds.ls(l=True, type="file"):
        # ensure this is actually part of this session and not referenced
        if cmds.referenceQuery(file_node, isNodeReferenced=True):
            # this is embedded in another reference, so don't include it in
            # the breakdown
            continue

        # get path and make it platform dependent
        # (maya uses C:/style/paths)
        texture_path = cmds.getAttr("%s.fileTextureName" % file_node).replace(
            "/", os.path.sep
        )
        if texture_path:
            ref_paths.add(texture_path)

    return list(ref_paths)


def _save_session(path):
    """
    Save the current session to the supplied path.
    """

    # Maya can choose the wrong file type so we should set it here
    # explicitly based on the extension
    maya_file_type = None
    if path.lower().endswith(".ma"):
        maya_file_type = "mayaAscii"
    elif path.lower().endswith(".mb"):
        maya_file_type = "mayaBinary"

    # Maya won't ensure that the folder is created when saving, so we must make sure it exists
    folder = os.path.dirname(path)
    ensure_folder_exists(folder)

    cmds.file(rename=path)

    # save the scene:
    if maya_file_type:
        cmds.file(save=True, force=True, type=maya_file_type)
    else:
        cmds.file(save=True, force=True)


# TODO: method duplicated in all the maya hooks
def _get_save_as_action():
    """
    Simple helper for returning a log action dict for saving the session
    """

    engine = sgtk.platform.current_engine()

    # default save callback
    callback = cmds.SaveScene

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





class MayaSceneArchiver:
    """
    Archive Maya scene with all dependencies including references.
    Creates a self-contained archive without modifying the current scene.
    """

    def __init__(self, output_directory):
        """
        Initialize archiver.

        :param output_directory: Directory where archive will be created
        """
        self.output_dir = output_directory
        self.archive_structure = {}
        self.collected_files = defaultdict(list)
        self.reference_mapping = {}
        self.temp_scene_path = None

    def create_archive(self, archive_name=None):
        """
        Create complete archive of current scene.

        :param archive_name: Optional name for archive (default: current scene name)
        :return: Path to archive directory
        """

        print("=" * 70)
        print("MAYA SCENE ARCHIVER")
        print("=" * 70)

        # Get current scene info
        current_scene = cmds.file(query=True, sceneName=True)

        if not current_scene:
            cmds.warning("Scene is not saved. Please save before archiving.")
            return None

        if not archive_name:
            archive_name = os.path.splitext(os.path.basename(current_scene))[0] + "_archive"

        # Create archive path inside output directory
        archive_path = os.path.join(self.output_dir, archive_name)

        print("\nOutput Directory: %s" % self.output_dir)
        print("Archive: %s" % archive_path)
        print("Source scene: %s" % current_scene)

        # Create archive structure
        self._create_directory_structure(archive_path)

        try:
            # Step 1: Duplicate scene in memory (don't modify original)
            print("\n[1/6] Creating temporary scene copy...")
            self._create_temp_scene_copy()

            # Step 2: Collect all file paths
            print("\n[2/6] Collecting file dependencies...")
            self._collect_all_files()

            # Step 3: Import references in temp scene
            print("\n[3/6] Processing references...")
            self._process_references()

            # Step 4: Copy all files to archive
            print("\n[4/6] Copying files to archive...")
            self._copy_files_to_archive()

            # Step 5: Save archived scene with updated paths
            print("\n[5/6] Saving archived scene...")
            archived_scene_path = self._save_archived_scene(archive_name)

            # Step 6: Create archive manifest
            print("\n[6/6] Creating archive manifest...")
            self._create_manifest(archive_path, archived_scene_path)

            # Restore original scene
            print("\nRestoring original scene...")
            self._restore_original_scene(current_scene)

            print("\n" + "=" * 70)
            print("ARCHIVE COMPLETE!")
            print("Location: %s" % archive_path)
            print("=" * 70)

            return archive_path

        except Exception as e:
            print("\nERROR during archiving: %s" % str(e))
            import traceback
            traceback.print_exc()

            # Restore original scene
            self._restore_original_scene(current_scene)

            return None

    def _create_directory_structure(self, archive_path):
        """Create archive directory structure."""

        self.archive_structure = {
            'scenes': os.path.join(archive_path, 'scenes'),
            'sourceimages': os.path.join(archive_path, 'sourceimages'),
            'references': os.path.join(archive_path, 'references'),
            'cache': os.path.join(archive_path, 'cache'),
            'particles': os.path.join(archive_path, 'particles'),
            'data': os.path.join(archive_path, 'data'),
            'clips': os.path.join(archive_path, 'clips'),
            'sound': os.path.join(archive_path, 'sound'),
            'movies': os.path.join(archive_path, 'movies'),
        }

        for folder_path in self.archive_structure.values():
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)
                print("  Created: %s" % folder_path)

    def _create_temp_scene_copy(self):
        """Create temporary copy of scene in memory."""

        import tempfile

        # Save current scene to temp location
        temp_dir = tempfile.gettempdir()
        temp_filename = "maya_archive_temp_%s.ma" % os.getpid()
        self.temp_scene_path = os.path.join(temp_dir, temp_filename)

        # Save current scene state
        cmds.file(rename=self.temp_scene_path)
        cmds.file(save=True, type='mayaAscii')

        print("  Temporary scene created: %s" % self.temp_scene_path)

    def _collect_all_files(self):
        """Collect all file dependencies in the scene."""

        # Textures
        print("\n  Collecting textures...")
        self._collect_file_nodes()

        # Image planes
        print("  Collecting image planes...")
        self._collect_image_planes()

        # Caches (Alembic, GPU, etc.)
        print("  Collecting caches...")
        self._collect_caches()

        # Audio files
        print("  Collecting audio...")
        self._collect_audio()

        # References
        print("  Collecting references...")
        self._collect_references()

        # IES files
        print("  Collecting IES files...")
        self._collect_ies_files()

        # Arnold standins
        print("  Collecting Arnold standins...")
        self._collect_arnold_standins()

        # Print summary
        total_files = sum(len(files) for files in self.collected_files.values())
        print("\n  Total files collected: %d" % total_files)

        for category, files in self.collected_files.items():
            if files:
                print("    %s: %d" % (category, len(files)))

    def _collect_file_nodes(self):
        """Collect texture files from file nodes."""

        file_nodes = cmds.ls(type='file')

        for file_node in file_nodes:
            try:
                file_path = cmds.getAttr(file_node + '.fileTextureName')

                if file_path and os.path.exists(file_path):
                    self.collected_files['textures'].append({
                        'source': file_path,
                        'node': file_node,
                        'attr': 'fileTextureName'
                    })
            except:
                pass

    def _collect_image_planes(self):
        """Collect image plane files."""

        image_planes = cmds.ls(type='imagePlane')

        for image_plane in image_planes:
            try:
                image_path = cmds.getAttr(image_plane + '.imageName')

                if image_path and os.path.exists(image_path):
                    self.collected_files['image_planes'].append({
                        'source': image_path,
                        'node': image_plane,
                        'attr': 'imageName'
                    })
            except:
                pass

    def _collect_caches(self):
        """Collect cache files (Alembic, GPU cache, etc.)."""

        # Alembic caches
        abc_nodes = cmds.ls(type='AlembicNode')
        for abc_node in abc_nodes:
            try:
                abc_file = cmds.getAttr(abc_node + '.abc_File')

                if abc_file and os.path.exists(abc_file):
                    self.collected_files['caches'].append({
                        'source': abc_file,
                        'node': abc_node,
                        'attr': 'abc_File'
                    })
            except:
                pass

        # GPU caches
        gpu_nodes = cmds.ls(type='gpuCache')
        for gpu_node in gpu_nodes:
            try:
                cache_file = cmds.getAttr(gpu_node + '.cacheFileName')

                if cache_file and os.path.exists(cache_file):
                    self.collected_files['caches'].append({
                        'source': cache_file,
                        'node': gpu_node,
                        'attr': 'cacheFileName'
                    })
            except:
                pass

        # nCache
        cache_files = cmds.ls(type='cacheFile')
        for cache_file_node in cache_files:
            try:
                cache_path = cmds.getAttr(cache_file_node + '.cachePath')
                cache_name = cmds.getAttr(cache_file_node + '.cacheName')

                if cache_path and cache_name:
                    full_path = os.path.join(cache_path, cache_name)

                    if os.path.exists(full_path):
                        self.collected_files['caches'].append({
                            'source': full_path,
                            'node': cache_file_node,
                            'attr': 'cachePath'
                        })
            except:
                pass

    def _collect_audio(self):
        """Collect audio files."""

        audio_nodes = cmds.ls(type='audio')

        for audio_node in audio_nodes:
            try:
                audio_file = cmds.getAttr(audio_node + '.filename')

                if audio_file and os.path.exists(audio_file):
                    self.collected_files['audio'].append({
                        'source': audio_file,
                        'node': audio_node,
                        'attr': 'filename'
                    })
            except:
                pass

    def _collect_references(self):
        """Collect reference files."""

        references = cmds.file(query=True, reference=True) or []

        for ref_path in references:
            if os.path.exists(ref_path):
                try:
                    ref_node = cmds.referenceQuery(ref_path, referenceNode=True)

                    self.collected_files['references'].append({
                        'source': ref_path,
                        'node': ref_node,
                        'namespace': cmds.referenceQuery(ref_path, namespace=True)
                    })
                except:
                    pass

    def _collect_ies_files(self):
        """Collect IES light profile files (Arnold, etc.)."""

        # Arnold lights
        arnold_lights = cmds.ls(type='aiPhotometricLight')

        for light in arnold_lights:
            try:
                ies_file = cmds.getAttr(light + '.aiFilename')

                if ies_file and os.path.exists(ies_file):
                    self.collected_files['ies'].append({
                        'source': ies_file,
                        'node': light,
                        'attr': 'aiFilename'
                    })
            except:
                pass

    def _collect_arnold_standins(self):
        """Collect Arnold standin (.ass) files."""

        standins = cmds.ls(type='aiStandIn')

        for standin in standins:
            try:
                dso_path = cmds.getAttr(standin + '.dso')

                if dso_path and os.path.exists(dso_path):
                    self.collected_files['standins'].append({
                        'source': dso_path,
                        'node': standin,
                        'attr': 'dso'
                    })
            except:
                pass

    def _process_references(self):
        """Import all references into the temp scene."""

        if not self.collected_files['references']:
            print("  No references to process")
            return

        # Get all references
        references = cmds.file(query=True, reference=True) or []

        print("  Found %d reference(s)" % len(references))

        # Import each reference (in reverse to handle nested refs)
        references.reverse()

        for ref_path in references:
            try:
                ref_node = cmds.referenceQuery(ref_path, referenceNode=True)
                namespace = cmds.referenceQuery(ref_path, namespace=True)

                print("    Importing: %s (namespace: %s)" % (
                    os.path.basename(ref_path),
                    namespace
                ))

                # Import reference
                cmds.file(ref_path, importReference=True, referenceNode=ref_node)

                # Store mapping
                self.reference_mapping[ref_node] = {
                    'original_path': ref_path,
                    'namespace': namespace
                }

            except Exception as e:
                print("    WARNING: Could not import reference %s: %s" % (ref_path, str(e)))

        print("  All references imported")

    def _copy_files_to_archive(self):
        """Copy all collected files to archive."""

        copied_count = 0

        for category, files in self.collected_files.items():
            if not files:
                continue

            print("\n  Copying %s..." % category)

            # Determine target directory
            if category == 'textures':
                target_dir = self.archive_structure['sourceimages']
            elif category == 'references':
                target_dir = self.archive_structure['references']
            elif category in ['caches', 'standins']:
                target_dir = self.archive_structure['cache']
            elif category == 'audio':
                target_dir = self.archive_structure['sound']
            elif category == 'image_planes':
                target_dir = self.archive_structure['sourceimages']
            elif category == 'ies':
                target_dir = self.archive_structure['data']
            else:
                target_dir = self.archive_structure['data']

            for file_info in files:
                source_path = file_info['source']

                if not os.path.exists(source_path):
                    print("    WARNING: File not found: %s" % source_path)
                    continue

                # Generate unique filename to avoid conflicts
                filename = os.path.basename(source_path)
                target_path = os.path.join(target_dir, filename)

                # Handle duplicate filenames
                counter = 1
                base_name, ext = os.path.splitext(filename)

                while os.path.exists(target_path):
                    filename = "%s_%d%s" % (base_name, counter, ext)
                    target_path = os.path.join(target_dir, filename)
                    counter += 1

                try:
                    # Copy file
                    shutil.copy2(source_path, target_path)

                    # Update file info with new path
                    file_info['archive_path'] = target_path
                    file_info['relative_path'] = os.path.relpath(target_path, self.output_dir)

                    copied_count += 1

                    # Update path in scene (for non-reference files)
                    if category != 'references' and 'node' in file_info and 'attr' in file_info:
                        try:
                            cmds.setAttr(
                                file_info['node'] + '.' + file_info['attr'],
                                target_path,
                                type='string'
                            )
                        except:
                            pass

                except Exception as e:
                    print("    ERROR copying %s: %s" % (filename, str(e)))

        print("\n  Total files copied: %d" % copied_count)

    def _save_archived_scene(self, archive_name):
        """Save the archived scene with updated paths."""

        archived_scene_path = os.path.join(
            self.archive_structure['scenes'],
            archive_name + '.ma'
        )

        # Rename and save
        cmds.file(rename=archived_scene_path)
        cmds.file(save=True, type='mayaAscii')

        print("  Archived scene saved: %s" % archived_scene_path)

        return archived_scene_path

    def _create_manifest(self, archive_path, archived_scene_path):
        """Create JSON manifest with archive information."""

        manifest_path = os.path.join(archive_path, 'archive_manifest.json')

        manifest = {
            'archive_name': os.path.basename(archive_path),
            'creation_date': cmds.date(),
            'maya_version': cmds.about(version=True),
            'archived_scene': os.path.relpath(archived_scene_path, archive_path),
            'file_counts': {
                category: len(files)
                for category, files in self.collected_files.items()
            },
            'total_files': sum(len(files) for files in self.collected_files.values()),
            'references_imported': len(self.reference_mapping),
            'structure': {
                key: os.path.relpath(path, archive_path)
                for key, path in self.archive_structure.items()
            }
        }

        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)

        print("  Manifest created: %s" % manifest_path)

    def _restore_original_scene(self, original_scene_path):
        """Restore the original scene without changes."""

        # Open original scene
        cmds.file(original_scene_path, open=True, force=True)

        # Clean up temp file
        if self.temp_scene_path and os.path.exists(self.temp_scene_path):
            try:
                os.remove(self.temp_scene_path)
            except:
                pass

        print("Original scene restored: %s" % original_scene_path)


# ============================================================================
# USAGE FUNCTIONS
# ============================================================================

def archive_current_scene(output_directory, archive_name=None):
    """
    Archive the current Maya scene with all dependencies.

    :param output_directory: Directory where archive folder will be created
    :param archive_name: Optional name for archive folder
    :return: Path to archive directory

    Usage:
        # Archive to specific directory
        archive_path = archive_current_scene('D:/archives')

        # Archive with custom name
        archive_path = archive_current_scene('D:/archives', 'shot010_v003')

        # Result will be: D:/archives/shot010_v003/
    """

    # Validate output directory
    if not os.path.exists(output_directory):
        try:
            os.makedirs(output_directory)
            print("Created output directory: %s" % output_directory)
        except Exception as e:
            cmds.error("Cannot create output directory: %s" % str(e))
            return None

    archiver = MayaSceneArchiver(output_directory)
    return archiver.create_archive(archive_name)


def archive_scene_interactive():
    """
    Interactive version - prompts user for output directory.
    """

    import maya.cmds as cmds

    # Prompt for output directory
    output_dir = cmds.fileDialog2(
        dialogStyle=2,
        fileMode=3,  # Directory mode
        caption='Select Archive Output Directory'
    )

    if not output_dir:
        print("Archive cancelled")
        return None

    output_dir = output_dir[0]

    # Get current scene name for default archive name
    current_scene = cmds.file(query=True, sceneName=True)

    if current_scene:
        default_name = os.path.splitext(os.path.basename(current_scene))[0] + "_archive"
    else:
        default_name = "maya_scene_archive"

    # Prompt for archive name
    result = cmds.promptDialog(
        title='Archive Name',
        message='Enter archive name:',
        text=default_name,
        button=['OK', 'Cancel'],
        defaultButton='OK',
        cancelButton='Cancel',
        dismissString='Cancel'
    )

    if result == 'OK':
        archive_name = cmds.promptDialog(query=True, text=True)
        return archive_current_scene(output_dir, archive_name)

    return None


def archive_to_project_archives_folder(archive_name=None):
    """
    Archive to the current project's 'archives' folder.
    Creates 'archives' folder in project if it doesn't exist.

    :param archive_name: Optional archive name
    :return: Path to archive

    Usage:
        archive_path = archive_to_project_archives_folder('shot010_final')
    """

    # Get current project path
    workspace = cmds.workspace(query=True, rootDirectory=True)

    if not workspace:
        cmds.warning("No project set. Please set a project first.")
        return None

    # Create archives folder in project
    archives_folder = os.path.join(workspace, 'archives')

    if not os.path.exists(archives_folder):
        os.makedirs(archives_folder)
        print("Created archives folder: %s" % archives_folder)

    return archive_current_scene(archives_folder, archive_name)


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

"""
# Basic usage - archive to specific folder:
archive_path = archive_current_scene('D:/my_archives')
# Result: D:/my_archives/scene_name_archive/

# With custom archive name:
archive_path = archive_current_scene('D:/my_archives', 'shot010_anim_v003')
# Result: D:/my_archives/shot010_anim_v003/

# Interactive with dialogs:
archive_path = archive_scene_interactive()

# Archive to project's archives folder:
archive_path = archive_to_project_archives_folder('final_delivery')
# Result: /current/project/archives/final_delivery/

# Windows paths:
archive_path = archive_current_scene('C:/Users/Artist/Desktop/archives')

# Network paths:
archive_path = archive_current_scene('//server/shared/maya_archives')

# Relative to current project:
import maya.cmds as cmds
project_path = cmds.workspace(query=True, rootDirectory=True)
output_dir = os.path.join(project_path, 'deliveries')
archive_path = archive_current_scene(output_dir, 'final_v001')
"""
