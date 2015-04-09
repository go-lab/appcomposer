import datetime
import traceback
import requests

from appcomposer import db
from appcomposer.models import RepositoryApp
from appcomposer.translator.utils import get_cached_session, extract_metadata_information

GOLAB_REPO = u'golabz'
EXTERNAL_REPO = u'external'

DEBUG = True

def download_golab_translations():
    cached_requests = get_cached_session()
    try:
        apps_response = cached_requests.get("http://www.golabz.eu/rest/apps/retrieve.json")
        apps = apps_response.json()
    except requests.RequestException:
        traceback.print_exc()

    if not apps_response.from_cache:
        pass # TODO: ignore some steps


    apps_by_url = {}
    for app in apps:
        apps_by_url[app['app_url']] = app

    apps_by_id = {}
    for app in apps:
        apps_by_id[unicode(app['id'])] = app

    #
    # This requires several steps.
    #
    # Step 1: synchronize with the golabz repo
    ##########################################
    #
    # Delete deprecated apps
    #
    stored_apps = db.session.query(RepositoryApp).filter_by(repository=GOLAB_REPO).all()

    stored_ids = []

    for stored_app in stored_apps:
        external_id = unicode(stored_app.external_id)
        if external_id not in apps_by_id:
            print stored_app.url, "not in the golabz repo anymore. Remove visibility?"
            # TODO
            pass
        else:
            stored_ids.append(external_id)
            # TODO: update
            app = apps_by_id[external_id]
            if app['app_url'] != stored_app.url:
                # TODO: update everything accordingly
                pass
            else:
                app_response = cached_requests.get(app['app_url'])
                if not app_response.from_cache:
                    # TODO: check each field
                    pass


    #
    # Add new apps
    #
    for app in apps:
        if app['id'] not in stored_ids:
            _add_new_app(cached_requests, repository = GOLAB_REPO, 
                            app_url = app['app_url'], title = app['title'], external_id = app['id'],
                            app_thumb = app['app_thumb'], description = app['description'])

    db.session.commit()

def _add_new_app(cached_requests, repository, app_url, title, external_id, app_thumb, description):
    now = datetime.datetime.now()

    failing = False
    # force_reload is True when adding a new application
    force_reload = False
    try:
        metadata_information = extract_metadata_information(app_url, cached_requests, force_reload = force_reload)
    except Exception:
        print
        print "Error on %s" % app_url
        traceback.print_exc()
        metadata_information = {}
        failing = True

    if DEBUG:
        print
        print "New app", title
        print app_url
        print metadata_information

    repo_app = RepositoryApp(name = title, url = app_url, external_id = external_id, repository = repository)
    repo_app.app_thumb = app_thumb
    repo_app.description = description

    repo_app.translatable = metadata_information.get('translatable', False)
    repo_app.adaptable = metadata_information.get('adaptable', False)
    repo_app.original_translations = u','.join(metadata_information.get('original_translations', {}).keys())

    repo_app.last_change = now
    repo_app.last_check = now

    if failing:
        repo_app.failing = True
        repo_app.failing_since = now

    db.session.add(repo_app)

    # TODO: call ops

if __name__ == '__main__':
    from appcomposer import app as my_app
    with my_app.app_context():
        download_golab_translations()
