angular
    .module('translateApp')
    .controller('LangTargetController', LangTargetController);


function LangTargetController($scope, $rootScope) {

    //////////////////
    // Initializations
    //////////////////


    /////////////////
    // Scope-related
    /////////////////

    /* SCOPE DATA */

    $scope.selected = {};

    $scope.objectKeys = $rootScope.objectKeys;
    $scope.all_languages = $rootScope.all_languages;
    $scope.all_groups = $rootScope.all_groups;


    // If we don't initialize it, the ui-select does not work.
    $scope.add = {};


    /* SCOPE METHODS */

    $scope.filteredObjectKeys = filteredObjectKeys;
    $scope.onTargetSelected = onTargetSelected;

    /* SCOPE WATCHES */

    // Initialize the default value when it is ready.
    $scope.$watch("appinfo.translations", function (newval, oldval) {
        if (newval != undefined)
            $scope.selected.lang = "all_ALL";
    });

    // Handle the selected event for the Lang field.
    $scope.$watch("selected.lang", onLangSelected);

    // Handle the selected event for the Target field.
    $scope.$watch("selected.target", onTargetSelected);


    ///////////////////
    // Implementations
    ///////////////////

    /**
     * Filters the specified map.
     * @param map
     * @param search
     * @returns {*}
     */
    function filteredObjectKeys(map, search) {
        var keys = Object.keys(map);
        var filteredKeys = [];

        if (search.length == 0)
            return keys;

        angular.forEach(keys, function (lang, index) {
            var text = $scope.appinfo.translations[lang].name;
            if (text.toLowerCase().indexOf(search.toLowerCase()) != -1)
                filteredKeys.push(lang);
        });

        return filteredKeys;
    }

    function onLangSelected(newval, oldval) {
        if (newval == undefined)
            return;

        $scope.selected.lang_info = $scope.appinfo.translations[$scope.selected.lang];

        $scope.selected.target = "ALL";
        $scope.onTargetSelected();
    }

    function onTargetSelected(newval, oldval) {
        if (newval == undefined)
            return;

        $scope.selected.target_info = $scope.selected.lang_info.targets[$scope.selected.target];
    }

} // !LangTargetController