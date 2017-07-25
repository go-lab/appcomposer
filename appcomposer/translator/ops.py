import urlparse
import hashlib
import datetime
from collections import defaultdict

from sqlalchemy import func, or_, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload_all

from appcomposer import db
from appcomposer.application import app
from appcomposer.languages import obtain_languages, obtain_groups
from appcomposer.translator.suggestions import translate_texts
from appcomposer.models import TranslatedApp, TranslationUrl, TranslationBundle, ActiveTranslationMessage, TranslationMessageHistory, TranslationKeySuggestion, TranslationValueSuggestion, GoLabOAuthUser, TranslationSyncLog, TranslationCurrentActiveUser, TranslationSubscription, TranslationNotificationRecipient, RepositoryApp

DEBUG = False

LANGUAGES = obtain_languages()
GROUPS = obtain_groups()

def get_golab_default_user():
    default_email = app.config.get('TRANSLATOR_DEFAULT_EMAIL', 'weblab+appcomposer@deusto.es')
    default_user = db.session.query(GoLabOAuthUser).filter_by(email = default_email).first()
    if default_user is None:
        default_user = GoLabOAuthUser(email = default_email, display_name = "AppComposer")
        db.session.add(default_user)
        try:
            db.session.commit()
        except IntegrityError:
            default_user = db.session.query(GoLabOAuthUser).filter_by(email = default_email).first()
            db.session.rollback()
        except:
            db.session.rollback()
            raise
    return default_user

def _get_or_create_app(app_url, translation_url, metadata):
    # Create the translation url if not present
    automatic = metadata.get('automatic', True)
    attribs = metadata.get('attribs', '')
    db_translation_url = db.session.query(TranslationUrl).filter_by(url = translation_url).first()
    if not db_translation_url:
        db_translation_url = TranslationUrl(url = translation_url, automatic = automatic, attribs = attribs)
        db.session.add(db_translation_url)
    else:
        if db_translation_url.automatic != automatic:
            db_translation_url.automatic = automatic
        if db_translation_url.attribs != attribs:
            db_translation_url.attribs = attribs

    SUBSCRIPTION_MECHANISM = 'translation-url'
    subscribed_emails = set([ email for email, in db.session.query(TranslationNotificationRecipient.email).filter(TranslationSubscription.translation_url == db_translation_url, TranslationSubscription.mechanism == SUBSCRIPTION_MECHANISM, TranslationSubscription.recipient_id == TranslationNotificationRecipient.id).all() ])

    subscription_requests = set(metadata.get('mails', []))
    
    pending_subscriptions = subscription_requests - subscribed_emails
    subscriptions_to_delete = subscribed_emails - subscription_requests

    if subscriptions_to_delete:
        for db_subscription in db.session.query(TranslationSubscription).filter(TranslationSubscription.mechanism == SUBSCRIPTION_MECHANISM, TranslationSubscription.translation_url == db_translation_url, TranslationSubscription.recipient_id == TranslationNotificationRecipient.id, TranslationNotificationRecipient.email.in_(list(subscriptions_to_delete))).all():
            db.session.delete(db_subscription)

    if pending_subscriptions:
        for pending_subscription in pending_subscriptions:
            recipient = db.session.query(TranslationNotificationRecipient).filter_by(email = pending_subscription).first()
            if not recipient:
                recipient = TranslationNotificationRecipient(pending_subscription)
                db.session.add(recipient)

            db.session.add(TranslationSubscription(translation_url = db_translation_url, recipient = recipient, mechanism = SUBSCRIPTION_MECHANISM))

    # Create the app if not present
    db_app_url = db.session.query(TranslatedApp).filter_by(url = app_url).first()
    if db_app_url:
        if db_app_url.translation_url is None:
            db_app_url.translation_url = db_translation_url
        elif db_app_url.translation_url != db_translation_url:
            # If present with a different translation url, copy the old one if possible
            _deep_copy_translations(db_app_url.translation_url, db_translation_url)
            db_app_url.translation_url = db_translation_url
    else:
        db_app_url = TranslatedApp(url = app_url, translation_url = db_translation_url)
    db.session.add(db_app_url)
    return db_translation_url

def _get_or_create_bundle(app_url, translation_url, metadata, language, target, from_developer):
    db_translation_url = _get_or_create_app(app_url, translation_url, metadata)

    # Create the bundle if not present
    db_translation_bundle = db.session.query(TranslationBundle).filter_by(translation_url = db_translation_url, language = language, target = target).first()
    if not db_translation_bundle:
        db_translation_bundle = TranslationBundle(language, target, db_translation_url, from_developer)
        db.session.add(db_translation_bundle)
    return db_translation_bundle

def get_bundles_by_key_namespaces(pairs):
    """ given a list of pairs (key, namespace), return the list of bundles which contain translations like those """
    keys = [ pair['key'] for pair in pairs ]
    namespaces = [ pair['namespace'] for pair in pairs if pair['namespace'] ]

    pairs_found = {}

    if keys and namespaces:
        for key, namespace, bundle_id in db.session.query(ActiveTranslationMessage.key, ActiveTranslationMessage.namespace, ActiveTranslationMessage.bundle_id).filter(ActiveTranslationMessage.key.in_(keys), ActiveTranslationMessage.namespace.in_(namespaces), ActiveTranslationMessage.taken_from_default == False).all():
            if (key, namespace) not in pairs_found:
                pairs_found[key, namespace] = set()
            pairs_found[key, namespace].add(bundle_id)

    bundle_ids = set()

    for pair in pairs:
        key = pair['key']
        namespace = pair['namespace']
        new_bundle_ids = pairs_found.get((key, namespace))
        if new_bundle_ids:
            bundle_ids.update(new_bundle_ids)

    bundles = []
    existing_bundles = []
    if bundle_ids:
        for lang, target in db.session.query(TranslationBundle.language, TranslationBundle.target).filter(TranslationBundle.id.in_(bundle_ids)).all():
            key = "%s@%s" % (target, lang)
            if key not in existing_bundles:
                existing_bundles.append(key)
                bundles.append({
                    'language' : lang,
                    'target' : target,
                })
    return bundles

def add_full_translation_to_app(user, app_url, translation_url, app_metadata, language, target, translated_messages, original_messages, from_developer):
    db_translation_bundle = _get_or_create_bundle(app_url, translation_url, app_metadata, language, target, from_developer)
    # 
    # <NO SHIELD NEW BEHAVIOR>
    # 
    #     We have recently removed the shields that protected messages to be overriden by users' messages.
    #     In the past, when a user attempted to update a message which was provided by the developer, we 
    #     automatically discarded it. Now we enable the user to delete it. Furthermore, if the developer
    #     changes a piece of text, and developers update it in their servers with a different message, we
    #     now give a higher priority to that message rather to that from the developer.
    # 
    if from_developer:
        # If it comes from the developer, now the expected thing is to check if it is different to the current message and, if it is different, check if it 
        # was different to the last message coming from the developer in the history with developer = True. If it is different (i.e., there has been really a chanage)
        # then proceed with the change. Otherwise, discard that message.
        # 
        # In other words, we have to do the translated_messages.pop() thing with those messages where there is a history and developer = True with the last message being equal
        if translated_messages is not None:
            translated_messages = translated_messages.copy()
            active_msgs = db.session.query(ActiveTranslationMessage).filter_by(bundle = db_translation_bundle).all()
            active_msgs_by_key = {  
                # key: value
            }
            for active_msg in active_msgs:
                active_msgs_by_key[active_msg.key] = active_msg.value

            # select atm.`key`, atm.value from TranslationMessageHistory atm 
            #         inner join (select max(datetime) as max_date, `key` from TranslationMessageHistory where from_developer = true and bundle_id = 953 group by bundle_id, `key`) atm2 
            #         on atm.datetime = atm2.max_date and atm.`key` = atm2.`key` where from_developer = true and bundle_id = 953;
            # 
            tmh_subquery = db.session.query(
                                    func.max(TranslationMessageHistory.datetime).label('tmh_date'), 
                                    TranslationMessageHistory.key.label('tmh_key')
                                ).filter_by(
                                    from_developer=True, 
                                    bundle=db_translation_bundle
                                ).group_by(
                                    TranslationMessageHistory.bundle_id, TranslationMessageHistory.key
                                ).subquery()

            latest_message_history = db.session.query(
                                TranslationMessageHistory.key, 
                                TranslationMessageHistory.value
                            ).join(
                                tmh_subquery, 
                                and_(
                                    tmh_subquery.c.tmh_date == TranslationMessageHistory.datetime, 
                                    tmh_subquery.c.tmh_key == TranslationMessageHistory.key
                                )
                            ).filter(
                                TranslationMessageHistory.from_developer == True, 
                                TranslationMessageHistory.bundle == db_translation_bundle
                            )

            historic_msgs_by_key = dict(latest_message_history.all())
                 # key: latest value from developer
            # }

            for key, value in historic_msgs_by_key.iteritems():
                # If the message is the same as it was in the latest message stored from developer,
                # and it comes from developer, do not take it into account (since it could be overriding
                # the user's message)
                if key in translated_messages and value == translated_messages[key] and translated_messages[key] != active_msgs_by_key.get(key):
                    translated_messages.pop(key, None)

    # 
    # </NO SHIELD NEW BEHAVIOR>
    # 

    if from_developer and not db_translation_bundle.from_developer:
        # If this is an existing translation and it comes from a developer, establish that it is from developer
        db_translation_bundle.from_developer = from_developer

    # 
    # # CODE COMMENTED as part of the no shield removal:
    # if not from_developer and db_translation_bundle.from_developer:
    #     # If this is an existing translation from a developer and it comes from a user (and not a developer)
    #     # then it should not be accepted.
    #     if translated_messages is not None:
    #         translated_messages = translated_messages.copy()
    #         for msg in db_translation_bundle.active_messages:
    #             if msg.from_developer:
    #                 translated_messages.pop(msg.key, None)
    #         # Continue with the remaining translated_messages

    if translated_messages is not None and len(translated_messages) == 0:
        translated_messages = None

    existing_namespaces = set()
    existing_namespace_keys = set()
    existing_active_translations_with_namespace_with_default_value = []
    
    # First, update translations

    for existing_active_translation in db.session.query(ActiveTranslationMessage).filter_by(bundle = db_translation_bundle).all():
        key = existing_active_translation.key

        position = original_messages.get(key, {}).get('position')
        if position is not None and existing_active_translation.position != position:
            existing_active_translation.position = position

        category = original_messages.get(key, {}).get('category')
        if existing_active_translation.category != category:
            existing_active_translation.category = category

        namespace = original_messages.get(key, {}).get('namespace')
        if existing_active_translation.namespace != namespace:
            existing_active_translation.namespace = namespace

        tool_id = original_messages.get(key, {}).get('tool_id')
        if existing_active_translation.tool_id != tool_id:
            existing_active_translation.tool_id = tool_id

        fmt = original_messages.get(key, {}).get('format')
        if existing_active_translation.fmt != fmt:
            existing_active_translation.fmt = fmt

        same_tool = original_messages.get(key, {}).get('same_tool')
        if existing_active_translation.same_tool != same_tool:
            existing_active_translation.same_tool = same_tool

        if namespace is not None and existing_active_translation.taken_from_default:
            existing_namespaces.add(namespace)
            existing_namespace_keys.add(key)
            existing_active_translations_with_namespace_with_default_value.append(existing_active_translation)
    
    # Then, check namespaces

    if existing_namespaces:
        # 
        # If there are namespaces in the current bundle with words taken from default, maybe those words are already translated somewhere else.
        # So I take the existing translations for that (namespace, key, bundle), and if they exist, I use them and delete the current message
        # 
        existing_namespace_translations = {}
        _user_ids = set()

        if existing_namespace_keys:
            for key, namespace, value, current_from_developer, existing_user_id in db.session.query(ActiveTranslationMessage.key, ActiveTranslationMessage.namespace, ActiveTranslationMessage.value, ActiveTranslationMessage.from_developer, TranslationMessageHistory.user_id).filter(ActiveTranslationMessage.history_id == TranslationMessageHistory.id, ActiveTranslationMessage.key.in_(list(existing_namespace_keys)), ActiveTranslationMessage.namespace.in_(list(existing_namespaces)), ActiveTranslationMessage.bundle_id == TranslationBundle.id, TranslationBundle.language == db_translation_bundle.language, TranslationBundle.target == db_translation_bundle.target, ActiveTranslationMessage.bundle_id != db_translation_bundle.id, ActiveTranslationMessage.taken_from_default == False).all():
                existing_namespace_translations[key, namespace] = (value, current_from_developer, existing_user_id)
                _user_ids.add(existing_user_id)

        existing_users = {}
        if _user_ids:
            for user in db.session.query(GoLabOAuthUser).filter(GoLabOAuthUser.id.in_(list(_user_ids))).all():
                existing_users[user.id] = user

        for wrong_message in existing_active_translations_with_namespace_with_default_value:
            now = datetime.datetime.utcnow()
            pack = existing_namespace_translations.get((wrong_message.key, wrong_message.namespace))
            if pack:
                value, current_from_developer, existing_user_id = pack
                existing_user = existing_users[existing_user_id]
                key = wrong_message.key
                wrong_history = wrong_message.history
                wrong_history_parent_id = wrong_history.id
                wrong_message_position = wrong_message.position
                wrong_message_category = wrong_message.category
                wrong_message_tool_id = wrong_message.tool_id
                wrong_message_same_tool = wrong_message.same_tool
                wrong_message_fmt = wrong_message.fmt

                # 1st) Delete the current translation message
                db.session.delete(wrong_message)

                # 2nd) Create a new historic translation message
                new_db_history = TranslationMessageHistory(db_translation_bundle, key, value, existing_user, now, wrong_history_parent_id, 
                                    taken_from_default = False, same_tool = wrong_message_same_tool, tool_id = wrong_message_tool_id, fmt = wrong_message_fmt, 
                                    position = wrong_message_position, category = wrong_message_category, from_developer = current_from_developer, namespace = wrong_message.namespace)
                db.session.add(new_db_history)

                # 3rd) Create a new active translation message
                new_db_active_translation_message = ActiveTranslationMessage(db_translation_bundle, key, value, new_db_history, now, False, wrong_message_position, wrong_message_category, current_from_developer, namespace, wrong_message_tool_id, wrong_message_same_tool, wrong_message_fmt)
                db.session.add(new_db_active_translation_message)

    if translated_messages is not None:
        # Delete active translations that are going to be replaced
        # Store which were the parents of those translations and
        # what existing translations don't need to be replaced
        unchanged = []
        parent_translation_ids = {}

        for existing_active_translation in db.session.query(ActiveTranslationMessage).filter_by(bundle = db_translation_bundle).all():
            key = existing_active_translation.key
            if key in translated_messages:
                if (translated_messages[key] and existing_active_translation.value != translated_messages[key]) or (not from_developer and existing_active_translation.taken_from_default):
                    parent_translation_ids[key] = existing_active_translation.history.id
                    db.session.delete(existing_active_translation)
                else:
                    unchanged.append(key)

        # For each translation message
        now = datetime.datetime.utcnow()
        for key, value in translated_messages.iteritems():
            if value is None:
                value = ""

            if key not in unchanged and key in original_messages:
                position = original_messages[key]['position']
                category = original_messages[key]['category']
                namespace = original_messages[key]['namespace']
                tool_id = original_messages[key]['tool_id']
                same_tool = original_messages[key]['same_tool']
                fmt = original_messages[key]['format']

                same_text_or_empty_text = original_messages.get(key, {}).get('text', object()) == value or (unicode(original_messages.get(key, {}).get('text', "non.empty.text")).strip() != "" and value.strip() == "")
                if from_developer and same_text_or_empty_text:
                    taken_from_default = True
                else:
                    taken_from_default = False

                # Create a new history message
                parent_translation_id = parent_translation_ids.get(key, None)
                db_history = TranslationMessageHistory(db_translation_bundle, key, value, user, now, parent_translation_id, taken_from_default = taken_from_default,
                                        same_tool = same_tool, tool_id = tool_id, fmt = fmt, position = position, category = category, from_developer = from_developer, namespace = namespace)
                db.session.add(db_history)

                # Establish that thew new active message points to this history message
                db_active_translation_message = ActiveTranslationMessage(db_translation_bundle, key, value, db_history, now, taken_from_default, position, category, from_developer, namespace, tool_id, same_tool, fmt)
                db.session.add(db_active_translation_message)

                if same_text_or_empty_text:
                    # If the message in the original language is the same as in the target language or the value is empty and it shouldn't, then
                    # it can be two things: 
                    # 
                    #   1) that it has been filled with the original language. In this case it should not be later displayed as a suggestion
                    #   2) that the message is the same in the original language and in the target language
                    # 
                    # Given that the original language will be a suggestion anyway, it's better to avoid storing this message as suggestion
                    continue


                if namespace:
                    # 
                    # If namespace, maybe this key is present in other translations. Therefore, I search for other translations
                    # out there in other bundles but with same language and target and the same namespace, where they are not from developer
                    # and I copy my translation to them.
                    # 
                    for wrong_message in db.session.query(ActiveTranslationMessage).filter(ActiveTranslationMessage.key == key, ActiveTranslationMessage.namespace == namespace, ActiveTranslationMessage.value != value, ActiveTranslationMessage.bundle_id == TranslationBundle.id, TranslationBundle.language == db_translation_bundle.language, TranslationBundle.target == db_translation_bundle.target, TranslationBundle.id != db_translation_bundle.id).options(joinedload_all('bundle')).all():
                        # wrong_message is a message for same language, target, key and namespace with a different value.
                        # We must update it with the current credentials
                        wrong_history = wrong_message.history
                        wrong_history_parent_id = wrong_history.id
                        wrong_message_position = wrong_message.position
                        wrong_message_category = wrong_message.category
                        wrong_message_bundle = wrong_message.bundle
                        wrong_message_tool_id = wrong_message.tool_id
                        wrong_message_same_tool = wrong_message.same_tool
                        wrong_message_fmt = wrong_message.fmt

                        # 1st) Delete the current translation message
                        db.session.delete(wrong_message)

                        # 2nd) Create a new historic translation message
                        new_db_history = TranslationMessageHistory(wrong_message_bundle, key, value, user, now, wrong_history_parent_id, taken_from_default = False,    
                                                                    same_tool = wrong_message_same_tool, tool_id = wrong_message_tool_id, fmt = wrong_message_fmt, 
                                                                    position = wrong_message_position, category = wrong_message_category, from_developer = from_developer, 
                                                                    namespace = namespace)
                        db.session.add(new_db_history)

                        # 3rd) Create a new active translation message
                        new_db_active_translation_message = ActiveTranslationMessage(wrong_message_bundle, key, value, new_db_history, now, False, wrong_message_position, wrong_message_category, from_developer, namespace, wrong_message_tool_id, wrong_message_same_tool, wrong_message_fmt)
                        db.session.add(new_db_active_translation_message)
                
                # Create a suggestion based on the key
                db_existing_key_suggestion = db.session.query(TranslationKeySuggestion).filter_by(key = key, value = value, language = language, target = target).first()
                if db_existing_key_suggestion:
                    db_existing_key_suggestion.number += 1
                    db.session.add(db_existing_key_suggestion)
                else:
                    db_key_suggestion = TranslationKeySuggestion(key = key, language = language, target = target, value = value, number = 1)
                    db.session.add(db_key_suggestion)

                # Create a suggestion based on the value
                if original_messages is not None and key in original_messages:
                    human_key = original_messages[key]['text'][:255]

                    db_existing_human_key_suggestion = db.session.query(TranslationValueSuggestion).filter_by(human_key = human_key, value = value, language = language, target = target).first()
                    if db_existing_human_key_suggestion:
                        db_existing_human_key_suggestion.number += 1
                        db.session.add(db_existing_human_key_suggestion)
                    else:
                        db_human_key_suggestion = TranslationValueSuggestion(human_key = human_key, language = language, target = target, value = value, number = 1)
                        db.session.add(db_human_key_suggestion)
        try:
            db.session.commit()
        except IntegrityError:
            # Somebody else concurrently run this
            db.session.rollback() 
        except:
            db.session.rollback()
            raise

    now = datetime.datetime.utcnow()
    existing_keys = [ key for key, in db.session.query(ActiveTranslationMessage.key).filter_by(bundle = db_translation_bundle).all() ]

    namespaces = [ v['namespace'] for k, v in original_messages.iteritems() if k not in existing_keys and v['namespace'] ]
    if namespaces:
        existing_namespaces = {}
        _user_ids = set()
        if original_messages and namespaces:
            for key, namespace, value, current_from_developer, existing_user_id in db.session.query(ActiveTranslationMessage.key, ActiveTranslationMessage.namespace, ActiveTranslationMessage.value, ActiveTranslationMessage.from_developer, TranslationMessageHistory.user_id).filter(ActiveTranslationMessage.history_id == TranslationMessageHistory.id, ActiveTranslationMessage.key.in_(original_messages.keys()), ActiveTranslationMessage.namespace.in_(list(namespaces)), ActiveTranslationMessage.bundle_id == TranslationBundle.id, TranslationBundle.language == db_translation_bundle.language, TranslationBundle.target == db_translation_bundle.target, ActiveTranslationMessage.taken_from_default == False).all():
                existing_namespaces[key, namespace] = (value, current_from_developer, existing_user_id)
                _user_ids.add(existing_user_id)

        existing_users = {}
        if _user_ids:
            for user in db.session.query(GoLabOAuthUser).filter(GoLabOAuthUser.id.in_(list(_user_ids))).all():
                existing_users[user.id] = user
    else:
        existing_namespaces = {}
        existing_users = {}

    for key, original_message_pack in original_messages.iteritems():
        if key not in existing_keys:
            value = original_message_pack['text'] or ''
            position = original_message_pack['position']
            category = original_message_pack['category']
            namespace = original_message_pack['namespace']
            tool_id = original_message_pack['tool_id']
            same_tool = original_message_pack['same_tool']
            fmt = original_message_pack['format']
            taken_from_default = True
            
            # If there is a namespace, try to get the value from other namespaces, and override the current value
            current_from_developer = False
            existing_user = user
            if namespace:
                pack = existing_namespaces.get((key, namespace), None)
                if pack is not None:
                    value, current_from_developer, existing_user_id = pack
                    existing_user = existing_users[existing_user_id]
                    taken_from_default = False

            # Create a new translation establishing that it was generated with the default value (and therefore it should be changed)
            db_history = TranslationMessageHistory(db_translation_bundle, key, value, existing_user, now, None, taken_from_default = taken_from_default,
                                                    same_tool = same_tool, tool_id = tool_id, fmt = fmt, position = position, category = category, 
                                                    from_developer = current_from_developer, namespace = namespace)
            db.session.add(db_history)
            
            # Establish that thew new active message points to this history message
            db_active_translation_message = ActiveTranslationMessage(db_translation_bundle, key, value, db_history, now, taken_from_default = taken_from_default, position = position, category = category, from_developer = current_from_developer, namespace = namespace, tool_id = tool_id, same_tool = same_tool, fmt = fmt)
            db.session.add(db_active_translation_message)

    for existing_key in existing_keys:
        if existing_key not in original_messages:
            old_translations = db.session.query(ActiveTranslationMessage).filter_by(bundle = db_translation_bundle, key = existing_key).all()
            for old_translation in old_translations:
                db.session.delete(old_translation)

    for key, namespace in db.session.query(ActiveTranslationMessage.key, ActiveTranslationMessage.namespace).filter_by(bundle = db_translation_bundle).group_by(ActiveTranslationMessage.key, ActiveTranslationMessage.namespace).having(func.count(ActiveTranslationMessage.key) > 1).all():
        best_chance = None
        all_chances = []
        for am in db.session.query(ActiveTranslationMessage).filter_by(key = key, namespace = namespace, bundle = db_translation_bundle).all():
            all_chances.append(am)
            if best_chance is None:
                best_chance = am
            elif not am.taken_from_default and best_chance.taken_from_default:
                best_chance = am
            elif am.from_developer and not best_chance.from_developer:
                best_chance = am
        for chance in all_chances:
            if chance != best_chance:
                db.session.delete(chance)

    # Commit!
    try:
        db.session.commit()
    except IntegrityError:
        # Somebody else did this
        db.session.rollback()
    except:
        db.session.rollback()
        raise
    
def register_app_url(app_url, translation_url, metadata):
    _get_or_create_app(app_url, translation_url, metadata)
    try:
        db.session.commit()
    except IntegrityError:
        # Somebody else did this process
        db.session.rollback()
    except:
        db.session.rollback()
        raise
    else:
        # Delay the synchronization process
        from appcomposer.translator.tasks import synchronize_single_app
        synchronize_single_app.delay(source="register app", single_app_url = synchronize_single_app)

def retrieve_stored(translation_url, language, target):
    db_translation_url = db.session.query(TranslationUrl).filter_by(url = translation_url).first()
    if db_translation_url is None:
        # Messages, from_developer, automatic
        return {}, False, True

    bundle = db.session.query(TranslationBundle).filter_by(translation_url = db_translation_url, language = language, target = target).first()

    if bundle is None:
        # No message, not from developer, automatic = whatever says before
        return {}, False, db_translation_url.automatic

    response = {}
    for message in bundle.active_messages:
        response[message.key] = {
            'value' : message.value,
            'from_default' : message.taken_from_default,
            'from_developer' : message.from_developer,
            'same_tool': message.same_tool,
            'tool_id': message.tool_id,
        }
    return response, bundle.from_developer, db_translation_url.automatic

SKIP_SUGGESTIONS_IF_STORED = False

def retrieve_suggestions(original_messages, language, target, stored_translations):
    original_keys = [ key for key in original_messages ]
    if SKIP_SUGGESTIONS_IF_STORED:
        original_keys = [ key for key in original_keys if key not in stored_translations ]
    original_values = [ original_messages[key]['text'] for key in original_keys ]
    original_keys_by_value = { 
        # value : [key1, key2]
    }
    for key, original_message_pack in original_messages.iteritems():
        value = original_message_pack['text']
        if value not in original_keys_by_value:
            original_keys_by_value[value] = []
        original_keys_by_value[value].append(key)

    all_suggestions = {}
    current_suggestions = []

    # First, key suggestions
    key_suggestions_by_key = defaultdict(list)
    if original_keys:
        for key_suggestion in db.session.query(TranslationKeySuggestion).filter_by(language = language, target = target).filter(TranslationKeySuggestion.key.in_(original_keys)).all():
            key_suggestions_by_key[key_suggestion.key].append({
                'target' : key_suggestion.value,
                'number' : key_suggestion.number,
            })
    current_suggestions.append(key_suggestions_by_key)

    # Second, value suggestions
    value_suggestions_by_key = defaultdict(list)
    orig_values = [ orig_value[:255] for orig_value in original_values ]
    if orig_values:
        for value_suggestion in db.session.query(TranslationValueSuggestion).filter_by(language = language, target = target).filter(TranslationValueSuggestion.human_key.in_(orig_values)).all():
            for key in original_keys_by_value.get(value_suggestion.human_key, []):
                value_suggestions_by_key[key].append({
                    'target' : value_suggestion.value,
                    'number' : value_suggestion.number,
                })

    for human_key, suggested_values in translate_texts(original_values, language).iteritems():
        for key in original_keys_by_value.get(human_key, []):
            for suggested_value, weight in suggested_values.iteritems():
                value_suggestions_by_key[key].append({
                    'target' : suggested_value,
                    'number' : weight,
                })

    current_suggestions.append(value_suggestions_by_key)

    for key in original_keys:
        current_key_suggestions = defaultdict(int)
        # { 'target' : number }

        for suggestions in current_suggestions:
            for suggestion in suggestions.get(key, []):
                current_key_suggestions[suggestion['target']] += suggestion['number']

        all_suggestions[key] = []
        if current_key_suggestions:
            # Normalize the maximum value
            total_value = max(current_key_suggestions.values())
            for target, number in current_key_suggestions.iteritems():
                normalized_value = 1.0 * number / total_value
                all_suggestions[key].append({
                    'target' : target,
                    'weight' : normalized_value,
                })
            all_suggestions[key].sort(lambda x1, x2: cmp(x1['weight'], x2['weight']), reverse = True)

    return all_suggestions

def _get_all_results_from_translation_url(translation_url, keys):
    if not keys:
        return []
    results = db.session.query(func.count(func.distinct(ActiveTranslationMessage.key)), func.max(ActiveTranslationMessage.datetime), func.min(ActiveTranslationMessage.datetime), TranslationBundle.language, TranslationBundle.target).filter(
                ActiveTranslationMessage.taken_from_default == False,
                ActiveTranslationMessage.same_tool == True,

                ActiveTranslationMessage.key.in_(keys),
                ActiveTranslationMessage.bundle_id == TranslationBundle.id, 
                TranslationBundle.translation_url_id == TranslationUrl.id, 

                TranslationUrl.url == translation_url,
            ).group_by(TranslationBundle.language, TranslationBundle.target).all()
    return results


def retrieve_translations_stats(translation_url, original_messages):
    filtered_messages = {
        # key: {
        #     typical properties (same_tool, tool_id, namespace...)
        # }
    }
    other_tools = {
        # tool_id : [ key1, key2, key3...],
    }
    for key, properties in original_messages.items():
        if properties['same_tool']:
            filtered_messages[key] = properties
        else:
            if properties['tool_id']:
                if properties['tool_id'] not in other_tools:
                    other_tools[properties['tool_id']] = []
                other_tools[properties['tool_id']].append(key)

    items = len(filtered_messages)
    results = _get_all_results_from_translation_url(translation_url, list(filtered_messages))

    if items == 0:
        return {}, []

    dependencies_data = {
        # (language, target) : [
        #      {
        #           "title": "My title",
        #           "link": "http://golabz.eu/...",
        #           "percent": 50,
        #           "translated": 10,
        #           "items": 20,
        #      }
        # ]
    }
    generic_dependencies = []
    translation_url_parsed = urlparse.urlparse(translation_url)
    translation_url_base = '{0}://{1}/'.format(translation_url_parsed.scheme, translation_url_parsed.netloc)
    if translation_url_base == 'http://go-lab.gw.utwente.nl/':
        tool_domain_condition = or_(
                TranslationUrl.url.like('{0}%'.format(translation_url_base)), # Check that it's from the same domain, and not other 'common' in other domain
                TranslationUrl.url.like('http://localhost:5000/%'),
                TranslationUrl.url.like('http://composer.golabz.eu/%'),
            )
    else:
        tool_domain_condition = TranslationUrl.url.like('{0}%'.format(translation_url_base)) # Check that it's from the same domain, and not other 'common' in other domain

    for tool_used, tool_keys in other_tools.items():
        tool_translation_urls = db.session.query(TranslationUrl.url).filter(
            tool_domain_condition,
            TranslationBundle.translation_url_id == TranslationUrl.id,
            ActiveTranslationMessage.bundle_id == TranslationBundle.id,
            ActiveTranslationMessage.tool_id == tool_used,
            ActiveTranslationMessage.same_tool == True,
        ).group_by(TranslationUrl.url).all()

        tool_translation_urls = [ url for url, in tool_translation_urls ]
        if tool_translation_urls:
            tool_translation_url = tool_translation_urls[0]

            tool_app_url_pack = db.session.query(TranslatedApp.url).filter(
                    TranslatedApp.translation_url_id == TranslationUrl.id,
                    TranslationUrl.url == tool_translation_url
                ).first()

            if tool_app_url_pack is not None:
                tool_app_url, = tool_app_url_pack
                repo_contents = db.session.query(RepositoryApp.name, RepositoryApp.app_link).filter(
                        RepositoryApp.url == TranslatedApp.url,
                        TranslatedApp.url == tool_app_url
                    ).first()
                if repo_contents is not None:
                    tool_name, tool_link = repo_contents 
                else:
                    tool_name = tool_app_url
                    tool_link = tool_app_url

                generic_dependencies.append({
                    'translated': 0,
                    'items': len(tool_keys),
                    'percent': 0.0,
                    'link': tool_link,
                    'title': tool_name,
                    'app_url': tool_app_url,
                })

                tool_results = _get_all_results_from_translation_url(tool_translation_url, tool_keys)
                
                for count, modification_date, creation_date, lang, target in tool_results:
                    if (lang, target) not in dependencies_data:
                        dependencies_data[lang, target] = []

                    dependencies_data[lang, target].append({
                        'translated': count,
                        'items': len(tool_keys),
                        'percent': (100.0 * count / len(tool_keys)) if len(tool_keys) > 0 else 1.0,
                        'link': tool_link,
                        'title': tool_name,
                        'app_url': tool_app_url,
                    })
                
                # After this, make sure we populate the rest of the languages too
                for count, modification_date, creation_date, lang, target in results:
                    # We don't care about count, modification_date or creation_date
                    if (lang, target) not in dependencies_data:
                        dependencies_data[lang, target] = []

                    all_tools_info = dependencies_data[lang, target]
                    found = False
                    for tools_info in all_tools_info:
                        if tools_info['app_url'] == tool_app_url:
                            found = True
                            break

                    if not found:
                        dependencies_data[lang, target].append({
                            'translated': 0,
                            'items': len(tool_keys),
                            'percent': 0.0,
                            'link': tool_link,
                            'title': tool_name,
                            'app_url': tool_app_url,
                        })

    translations = {
        # es_ES : {
        #      "name" : foo,
        #      "targets" : {
        #           "ALL" : {
        #                "modified_date" : "2014-02-14",
        #                "creation_date" : "2014-02-14",
        #                "name" : "Adolescens...,
        #                "translated" : 21,
        #                "items" : 31,
        #                "dependencies" : [
        #                    {
        #                        "title": "My dependency",
        #                        "link": "http://composer.golabz.eu/...",
        #                        "percent": 50,
        #                        "translated": 10,
        #                        "items": 20,
        #                    }
        #                ]
        #           }
        #      }
        # }
    }

    for count, modification_date, creation_date, lang, target in results:
        if lang not in translations:
            translations[lang] = {
                'name' : LANGUAGES.get(lang),
                'targets' : {}
            }

        mdate = modification_date.strftime("%Y-%m-%d") if modification_date is not None else None
        cdate = creation_date.strftime("%Y-%m-%d") if creation_date is not None else None
        dependencies = dependencies_data.get((lang, target), [])

        translations[lang]['targets'][target] = {
            'modification_date' : mdate,
            'creation_date' : cdate,
            'name' : GROUPS.get(target),
            'translated' : count,
            'items' : items,
            'dependencies': dependencies,
        }

    # Verify that all the info from the dependencies is displayed
    for (lang, target), dependencies in dependencies_data.iteritems():
        if lang not in translations:
            translations[lang] = {
                'name' : LANGUAGES.get(lang),
                'targets' : {}
            }

        if target not in translations[lang]['targets']:
            translations[lang]['targets'][target] = {
                'modification_date' : None,
                'creation_date' : None,
                'name' : GROUPS.get(target),
                'translated' : 0,
                'items' : items,
                'dependencies': dependencies,
            }   

    return translations, generic_dependencies


def retrieve_translations_percent(translation_url, original_messages):
    percent = {
        # es_ES_ALL : 0.8
    }

    translations_stats, generic_dependencies = retrieve_translations_stats(translation_url, original_messages)
    for lang, lang_package in translations_stats.iteritems():
        targets = lang_package.get('targets', {})
        for target, target_stats in targets.iteritems():
            translated = target_stats['translated']
            total_items = target_stats['items']
            percent['%s_%s' % (lang, target)] = (1.0 * translated / total_items) if total_items > 0 else 1.0

    return percent

def _deep_copy_bundle(src_bundle, dst_bundle):
    """Copy all the messages. Safely assume that there is no translation in the destination, so
    we can copy all the history, active, etc.
    """
    src_message_ids = {
        # old_id : new_id
    }
    historic = {
        # old_id : new historic instance
    }
    for msg in src_bundle.all_messages:
        t_history = TranslationMessageHistory(dst_bundle, msg.key, msg.value, msg.user, msg.datetime, src_message_ids.get(msg.parent_translation_id), msg.taken_from_default,
                                                same_tool = msg.same_tool, tool_id = msg.tool_id, fmt = msg.fmt, 
                                                position = msg.position, category = msg.category, from_developer = msg.from_developer, 
                                                namespace = msg.namespace)
        db.session.add(t_history)
        try:
            db.session.commit()
        except:
            db.session.rollback()
            raise
        db.session.refresh(t_history)
        src_message_ids[msg.id] = t_history.id
        historic[msg.id] = t_history

    now = datetime.datetime.utcnow()
    for msg in src_bundle.active_messages:
        history = historic.get(msg.history_id)
        active_t = ActiveTranslationMessage(dst_bundle, msg.key, msg.value, history, now, msg.taken_from_default, msg.position, msg.category, msg.from_developer, msg.namespace, msg.tool_id, msg.same_tool, msg.fmt)
        db.session.add(active_t)

    try:
        db.session.commit()
    except:
        db.session.rollback()
        raise

def _merge_bundle(src_bundle, dst_bundle):
    """Copy all the messages. The destination bundle already existed, so we can only copy those
    messages not present."""
    now = datetime.datetime.utcnow()
    for msg in src_bundle.active_messages:
        existing_translation = db.session.query(ActiveTranslationMessage).filter_by(bundle = dst_bundle, key = msg.key).first()
        if existing_translation is None:
            t_history = TranslationMessageHistory(dst_bundle, msg.key, msg.value, msg.history.user, now, None, msg.taken_from_default,
                                                same_tool = msg.same_tool, tool_id = msg.tool_id, fmt = msg.fmt, 
                                                position = msg.position, category = msg.category, from_developer = msg.from_developer, 
                                                namespace = msg.namespace)
            db.session.add(t_history)
            active_t = ActiveTranslationMessage(dst_bundle, msg.key, msg.value, t_history, now, msg.taken_from_default, msg.position, msg.category, msg.from_developer, msg.namespace, msg.tool_id, msg.same_tool, msg.fmt)
            db.session.add(active_t)
            try:
                db.session.commit()
            except:
                db.session.rollback()
                raise
        elif existing_translation.taken_from_default and not msg.taken_from_default:
            # Merge it
            t_history = TranslationMessageHistory(dst_bundle, msg.key, msg.value, msg.history.user, now, existing_translation.history.id, msg.taken_from_default,
                                                same_tool = msg.same_tool, tool_id = msg.tool_id, fmt = msg.fmt, 
                                                position = msg.position, category = msg.category, from_developer = msg.from_developer, 
                                                namespace = msg.namespace)

            db.session.add(t_history)
            active_t = ActiveTranslationMessage(dst_bundle, msg.key, msg.value, t_history, now, msg.taken_from_default, msg.position, msg.category, msg.from_developer, msg.namespace, msg.tool_id, msg.same_tool, msg.fmt)
            db.session.add(active_t)
            db.session.delete(existing_translation)
            try:
                db.session.commit()
            except:
                db.session.rollback()
                raise

def _deep_copy_translations(old_translation_url, new_translation_url):
    """Given an old translation of a URL, take the old bundles and copy them to the new one."""
    new_bundles = {}
    for new_bundle in new_translation_url.bundles:
        new_bundles[new_bundle.language, new_bundle.target] = new_bundle

    for old_bundle in old_translation_url.bundles:
        new_bundle = new_bundles.get((old_bundle.language, old_bundle.target))
        if new_bundle:
            _merge_bundle(old_bundle, new_bundle)
        else:
            new_bundle = TranslationBundle(old_bundle.language, old_bundle.target, new_translation_url, old_bundle.from_developer)
            db.session.add(new_bundle)
            _deep_copy_bundle(old_bundle, new_bundle)

def start_synchronization(source, cached, single_app_url = None):
    now = datetime.datetime.utcnow()
    sync_log = TranslationSyncLog(now, None, source, cached, single_app_url)
    db.session.add(sync_log)
    try:
        db.session.commit()
    except:
        db.session.rollback()
        raise
    db.session.refresh(sync_log)
    print "Starting synchronization %s" % sync_log.id
    return sync_log.id

def end_synchronization(sync_id, number):
    now = datetime.datetime.utcnow()
    sync_log = db.session.query(TranslationSyncLog).filter_by(id = sync_id).first()
    if sync_log is not None:
        sync_log.end_datetime = now
        sync_log.number_apps = number
        print "Synchronization %s finished" % sync_log.id
        try:
            db.session.commit()
        except:
            db.session.rollback()
            raise

def get_latest_synchronizations():
    latest_syncs = db.session.query(TranslationSyncLog).order_by(TranslationSyncLog.start_datetime.desc()).limit(10).all()
    return [
        {
            'id' : sync.id,
            'start' : sync.start_datetime,
            'end' : sync.end_datetime,
            'source' : sync.source,
            'cached' : sync.cached,
            'single_url' : sync.single_url,
            'number' : sync.number_apps,
        } for sync in latest_syncs
    ]

def update_user_status(language, target, app_url, user):
    translated_app = db.session.query(TranslatedApp).filter_by(url = app_url).first()
    if translated_app is None:
        return
    
    translation_url = translated_app.translation_url
    if translation_url is None:
        return

    bundle = db.session.query(TranslationBundle).filter_by(translation_url = translation_url, language = language, target = target).first()
    if bundle is None:
        return

    if user is None:
        print "ERROR: user can't be NULL"
        return

    active_user = db.session.query(TranslationCurrentActiveUser).filter_by(bundle = bundle, user = user).first()
    if active_user is None:
        active_user = TranslationCurrentActiveUser(user = user, bundle = bundle)
        db.session.add(active_user)
    else:
        active_user.update_last_check()
    
    try:
        db.session.commit()
    except:
        db.session.rollback()
        raise

def get_user_status(language, target, app_url, user):
    FORMAT = "%Y-%m-%dT%H:%M:%SZ"
    now = datetime.datetime.utcnow()
    now_str = now.strftime(FORMAT)

    ERROR = {
        'modificationDate': now_str,
        'modificationDateByOther': now_str,
        'time_now': now_str,
        'collaborators': []
    }
    translated_app = db.session.query(TranslatedApp).filter_by(url = app_url).first()
    if translated_app is None:
        ERROR['error_msg'] = "Translation App URL not found"
        return ERROR
    
    translation_url = translated_app.translation_url
    if translation_url is None:
        ERROR['error_msg'] = "Translation Translation URL not found"
        return ERROR

    bundle = db.session.query(TranslationBundle).filter_by(translation_url = translation_url, language = language, target = target).first()
    if bundle is None:
        ERROR['error_msg'] = "Bundle not found"
        return ERROR

    last_change_by_user = db.session.query(func.max(ActiveTranslationMessage.datetime), TranslationMessageHistory.user_id).filter(ActiveTranslationMessage.history_id == TranslationMessageHistory.id, ActiveTranslationMessage.bundle == bundle).group_by(TranslationMessageHistory.user_id).all()

    modification_date = None
    modification_date_by_other = None
    for last_change, user_id in last_change_by_user:
        if user_id == user.id:
            modification_date = last_change
        else:
            if modification_date_by_other is None or modification_date_by_other < last_change:
                modification_date_by_other = last_change

    if modification_date is None and modification_date_by_other is not None:
        modification_date = modification_date_by_other

    # Find collaborators (if any)
    latest_minutes = now - datetime.timedelta(minutes = 1)
    db_collaborators = db.session.query(TranslationCurrentActiveUser).filter(TranslationCurrentActiveUser.bundle == bundle, TranslationCurrentActiveUser.last_check > latest_minutes).all()
    collaborators = []
    for collaborator in db_collaborators:
        if collaborator.user != user and collaborator.user is not None:
            collaborators.append({
                'name' : collaborator.user.display_name,
                'md5' : hashlib.md5(collaborator.user.email).hexdigest(),
            })
    
    return {
        'modificationDate': modification_date.strftime(FORMAT) if modification_date is not None else None,
        'modificationDateByOther': modification_date_by_other.strftime(FORMAT) if modification_date_by_other is not None else None,
        'time_now': now_str,
        'collaborators': collaborators
    }

