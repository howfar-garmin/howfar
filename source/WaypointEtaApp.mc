import Toybox.Application;
import Toybox.Lang;
import Toybox.WatchUi;

class WaypointEtaApp extends Application.AppBase {
    hidden var _view as WaypointEtaView?;

    function initialize() {
        AppBase.initialize();
    }

    function getInitialView() {
        var view = new WaypointEtaView();
        _view = view;
        return [view];
    }

    // New strings pasted in Garmin Connect
    function onSettingsChanged() as Void {
        var view = _view;
        if (view != null) {
            view.loadSettings();
        }
        WatchUi.requestUpdate();
    }
}
