angular
    .module("translateApp")
    .controller("EditController", EditController);

function EditController($scope, $resource, $routeParams, $log, $modal) {

    /////////
    // Initialization
    /////////

    var TranslationInfo = $resource(APP_DYN_ROOT + "translate"); // Query parameters are needed
    var Appinfo = $resource(APP_DYN_ROOT + "api/apps");

    /////////
    // Scope related
    /////////

    $scope.params = $routeParams;
    $scope.appurl = $routeParams.appurl;

    $scope.bundle = {};
    $scope.bundle.appurl = $scope.appurl;
    $scope.bundle.srclang = "all_ALL";
    $scope.bundle.srcgroup = "ALL";
    $scope.bundle.targetlang = $routeParams.targetlang;
    $scope.bundle.targetgroup = $routeParams.targetgroup;

    $scope.appinfo = Appinfo.get({app_url: $scope.appurl});
    $scope.translationInfo = TranslationInfo.get({app_url: $scope.appurl, srclang: $scope.bundle.srclang,
        srcgroup: $scope.bundle.srcgroup, lang: $scope.bundle.targetlang, target: $scope.bundle.targetgroup});

    /* METHODS */

    $scope.changeSourceLanguage = changeSourceLanguage;

    /////////
    // Implementations
    /////////

    function changeSourceLanguage() {
        $log.debug("[changeSourceLanguage]");

        var modal = $modal.open({
            templateUrl: 'edit/change-source/change-source.modal.html',
            controller: 'ChangeSourceController',
            controllerAs: 'changeSourceController',
            backdrop: true,
            keyboard: true,
            size: 'lg',
            scope: $scope
        });

        modal.result.then(onSourceLanguageChanged, onSourceLanguageChangeDismissed);
    } // !changeSourceLanguage

    function onSourceLanguageChanged(selected) {
        $log.debug("[onSourceLanguageChanged]");

        $scope.bundle.srclang = selected.lang;
        $scope.bundle.srcgroup = selected.target;

        // TODO: Refresh only if we did not select the same source language.
        $scope.translationInfo = TranslationInfo.get({appurl: $scope.appurl, srclang: $scope.bundle.srclang,
            srcgroup: $scope.bundle.srcgroup, targetlang: $scope.bundle.targetlang, targetgroup: $scope.bundle.targetgroup});
    } // !onSourceLanguageChanged


    function onSourceLanguageChangeDismissed() {
        $log.debug("[onSourceLanguageChangeDismissed]");
    } // !onSourceLanguageChangeDismissed

} // !EditController