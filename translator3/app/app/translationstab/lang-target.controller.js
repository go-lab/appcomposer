angular
    .module('translateApp')
    .controller('LangTargetController', LangTargetController);


function LangTargetController($scope, $rootScope, $resource) {

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

    $scope.chooseLanguageError = "";


    /* SCOPE METHODS */

    $scope.filteredObjectKeys = filteredObjectKeys;

    $scope.languages = languages;
    $scope.onLangSelected = onLangSelected;


    /* SCOPE WATCHES */

    // Initialize the default value when it is ready.
    $scope.$watch("appinfo.translations", function (newval, oldval) {
        if (newval != undefined)
            $scope.selected.lang = undefined;
    });

    // Handle the selected event for the Lang field.
    $scope.$watch("selected.lang", onLangSelected);


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

    /**
     * Returns the list of languages to show.
     */
    function languages() {
        var all = $scope.objectKeys($scope.all_languages);
        var toremove = ["all_ALL"];

        return $(all).not(toremove).get();
    } // !languagesThatCanBeAdded


    /**
     * Event to be invoked when a language is selected.
     */
    function onLangSelected(newval, oldval) {
        if (newval == undefined)
            return;

        $scope.selected.lang_info = $scope.appinfo.translations[$scope.selected.lang];

        $scope.selected.target = "ALL";
    } // !onLangSelected


} // !LangTargetController