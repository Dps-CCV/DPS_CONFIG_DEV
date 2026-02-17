# Copyright (c) 2018 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

"""
Hook that gets executed every time a new Toolkit API instance is created.
"""

from tank import Hook
import os
import shutil
import stat
import sgtk

class TankInit(Hook):
    def execute(self, **kwargs):
        """
        Executed when a new Toolkit API instance is initialized.

        You can access the Toolkit API instance through ``self.parent``.

        The default implementation does nothing.
        """
        tk = self.parent
        engine = sgtk.platform.current_engine()
        if engine and engine.name == "tk-desktop":
            ##synchronize path cache
            tk.synchronize_filesystem_structure(full_sync=True)
            ##Delete old configs
            parent_folder = os.path.dirname(os.path.dirname(os.environ['CONFIG']))
            def fix_permissions(path):
                for root, dirs, files in os.walk(path, topdown=False):
                    for d in dirs:
                        os.chmod(os.path.join(root, d), stat.S_IWUSR)
                    for f in files:
                        os.chmod(os.path.join(root, f), stat.S_IWUSR)
            if os.environ.get("SGD_DESKTOP_SITE_INIT_DONE") == None:
                for c in os.listdir(parent_folder):
                    full_path = os.path.join(parent_folder, c)
                    if full_path not in config:
                        print(full_path)
                        os.chmod(full_path, stat.S_IWUSR)
                        fix_permissions(full_path)
                        shutil.rmtree(full_path)
            os.environ["SGD_DESKTOP_SITE_INIT_DONE"] = "1"
        pass
