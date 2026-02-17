python# config/hooks/tk-multi-workfiles2/ui_config_hook.py
# Fallback approach - monkey patch the entity model

import sgtk
from sgtk.platform.qt import QtCore, QtGui

HookBaseClass = sgtk.get_hook_baseclass()


class UiConfigHook(HookBaseClass):
    """
    Fallback approach using monkey patching for v0.16.0
    """

    def get_entity_tree_proxy_model(self, source_model, parent, **kwargs):
        """
        Inject sorting proxy model into entity tree.
        """
        try:
            proxy = AlphabeticalSortProxyModel(parent)
            proxy.setSourceModel(source_model)
            proxy.sort(0, QtCore.Qt.AscendingOrder)
            proxy.setDynamicSortFilter(True)
            return proxy
        except Exception as e:
            self.logger.warning(
                "Could not create sort proxy model: %s" % str(e)
            )
            return None


class AlphabeticalSortProxyModel(QtGui.QSortFilterProxyModel):
    """Sorts entity tree alphabetically at all hierarchy levels."""

    def lessThan(self, left, right):
        left_data = self.sourceModel().data(left, QtCore.Qt.DisplayRole)
        right_data = self.sourceModel().data(right, QtCore.Qt.DisplayRole)

        if left_data is None:
            return True
        if right_data is None:
            return False

        return str(left_data).lower() < str(right_data).lower()

    def filterAcceptsRow(self, source_row, source_parent):
        return Tru