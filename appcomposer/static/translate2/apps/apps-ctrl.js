angular
    .module("translateApp")
    .controller("AppsCtrl", AppsCtrl);


function AppsCtrl($scope, $resource, $compile, DTOptionsBuilder, DTColumnDefBuilder) {
    $scope.apps = $resource(APP_DYN_ROOT + "translations").query();
    $scope.dt = {};

    $scope.selected = {};
    $scope.selected.app = undefined; // To store the selected app.

    $scope.dt.columnDefs = [
        DTColumnDefBuilder.newColumnDef(0).notSortable().withOption("width", "30%"),
        DTColumnDefBuilder.newColumnDef(1).notSortable().withOption("width", "40%"),
        DTColumnDefBuilder.newColumnDef(2).notSortable()
    ];

    $scope.dt.options = DTOptionsBuilder.newOptions()
        .withPaginationType('full_numbers')
        .withDisplayLength(10)
        .withOption("autoWidth", true);



    $scope.completionToColor = completionToColor;
    $scope.selectApp = selectApp;
    $scope.isSelected = isSelected;

    $scope.$on('event:dataTableLoaded', dataTableLoadedHandler);


    /**
     * Get a reference to the jQuery DataTable.
     * @param evt
     * @param loadedDT
     */
    function dataTableLoadedHandler(evt, loadedDT) {
        $scope.dt = loadedDT;
    }

    /**
     * Converts a completion percent of a language into an appropriate
     * HTML color string.
     *
     * @param {float} completion: Completion from 0 to 1.
     * @return {string}: The HTML color. Fully green if 1, fully red if 0.
     */
    function completionToColor(completion) {
        return "FF0000";
    }

    /**
     * Selects an app in the list.
     * @param index: Index of the selected app.
     * @param app: The selected app.
     */
    function selectApp(app, index) {
        // Hide the previous selection.
        if($scope.selected.index !== undefined) {
            $scope.dt.DataTable.row($scope.selected.index).child().hide();
        }

        $scope.selected.app = app;
        $scope.selected.index = index;

        if($scope.dt != undefined) {
            var table = $scope.dt;
            var row = table.DataTable.row(index);
            var c = row.child($compile("<ac-app-details class='my-disabled-hover' app=selected.app></ac-app-details>")($scope));
            c.show();
        }
    }

    /**
     * Checks if the app is selected.
     * @param app
     */
    function isSelected(app) {
        if($scope.selected.app == undefined)
            return false;

        var result = app.title === $scope.selected.app.title;
        return result;
    }

}