import json
import codecs
import datetime
import os.path
import logging
import argparse
import sqlite3
import sys
import time

# The following Javascript will find an IG user's ID when executed in
# Google Chrome/Chromium's console. Doesn't seem to work in Firefox for
# some reason.

# window._sharedData.entry_data.ProfilePage[0].graphql.user.id

try:
    from instagram_private_api import (
        Client, ClientError, ClientLoginError,
        ClientCookieExpiredError, ClientLoginRequiredError,
        __version__ as client_version)
except ImportError:
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    from instagram_private_api import (
        Client, ClientError, ClientLoginError,
        ClientCookieExpiredError, ClientLoginRequiredError,
        __version__ as client_version)


def to_json(python_object):
    if isinstance(python_object, bytes):
        return {'__class__': 'bytes',
                '__value__': codecs.encode(python_object, 'base64').decode()}
    raise TypeError(repr(python_object) + ' is not JSON serializable')


def from_json(json_object):
    if '__class__' in json_object and json_object['__class__'] == 'bytes':
        return codecs.decode(json_object['__value__'].encode(), 'base64')
    return json_object


def onlogin_callback(api, new_settings_file):
    cache_settings = api.settings
    with open(new_settings_file, 'w') as outfile:
        json.dump(cache_settings, outfile, default=to_json)
        print('SAVED: {0!s}'.format(new_settings_file))


def main(api, database, node_type, user_list):
    logger = logging.getLogger("ig_followers")
    logger.setLevel(logging.INFO)
    with sqlite3.connect(database) as conn:
        cur = conn.cursor()
        try:
            for user_pair in user_list:
                userid, sep, url = user_pair.partition(',')
                username = url[url[:-1].rfind('/')+1:-1]
                cur.execute("INSERT OR REPLACE INTO NODE "
                            "(USER_ID, USERNAME, URL, NODE_TYPE, IS_VERIFIED) VALUES (?,?,?,?,?)",
                    (userid, username, url, node_type, 0))
                logger.info('Querying user {}'.format(username))

                following_count = 0
                following_uuid = Client.generate_uuid()
                following = api.user_following(userid, following_uuid)
                next_max_id = following.get('next_max_id')
                while True:
                    for foll in following['users']:
                        cur.execute("INSERT OR IGNORE INTO NODE "
                                    "(USER_ID, USERNAME, URL, NODE_TYPE, IS_VERIFIED) VALUES (?,?,?,?,?)",
                            (foll['pk'],
                             foll['username'],
                             'https://instagram.com/{}/'.format(foll['username']),
                             None,
                             foll['is_verified']))
                        cur.execute("INSERT OR IGNORE INTO EDGE "
                                    "(FROM_ID, TO_ID, DESCRIPTION) VALUES (?,?,?)",
                            (userid, foll['pk'], ''))

                    following_count += len(following['users'])
                    time.sleep(3)
                    logger.info(following_count)
                    if not next_max_id:
                        break
                    tries = 3
                    while tries > 0:
                        try:
                            following = api.user_following(userid, following_uuid, max_id=next_max_id)
                            break
                        except ConnectionResetError as e:
                            tries -= 1
                            if tries == 0:
                                #raise
                                logger.info('Too many retries - skipping remainder.')
                                continue
                            logger.info('Connection reset - retrying')
                            time.sleep(10)
                    
                    next_max_id = following.get('next_max_id')

                logger.info('Found {} accounts followed by {}'.format(following_count, username))
                conn.commit()

                follower_count = 0
                follower_uuid = Client.generate_uuid()
                followers = api.user_followers(userid, follower_uuid)
                next_max_id = followers.get('next_max_id')
                while True:
                    for foll in followers['users']:
                        cur.execute("INSERT OR IGNORE INTO NODE "
                                    "(USER_ID, USERNAME, URL, NODE_TYPE, IS_VERIFIED) VALUES (?,?,?,?,?)",
                            (foll['pk'],
                             foll['username'],
                             'https://instagram.com/{}/'.format(foll['username']),
                             None,
                             foll['is_verified']))
                        cur.execute("INSERT OR IGNORE INTO EDGE "
                                    "(FROM_ID, TO_ID, DESCRIPTION) VALUES (?,?,?)",
                            (foll['pk'], userid, ''))

                    follower_count += len(followers['users'])
                    time.sleep(3)
                    logger.info(follower_count)
                    if not next_max_id:
                        break
                    tries = 3
                    while tries > 0:
                        try:
                            followers = api.user_followers(userid, follower_uuid, max_id=next_max_id)
                            break
                        except ConnectionResetError as e:
                            tries -= 1
                            if tries == 0:
                                #raise
                                logger.info('Too many retries - skipping remainder.')
                                continue
                            logger.info('Connection reset - retrying')
                            time.sleep(10)
                    next_max_id = followers.get('next_max_id')

                logger.info('Found {} accounts following {}'.format(follower_count, username))
                conn.commit()

                time.sleep(3)
                

            conn.commit()
        finally:
            cur.close()

if __name__ == '__main__':

    logging.basicConfig()
    logger = logging.getLogger('instagram_private_api')
    logger.setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(description='login callback and save settings demo')
    parser.add_argument('-settings', '--settings', dest='settings_file_path', type=str, required=True)
    parser.add_argument('-u', '--username', dest='username', type=str, required=True)
    parser.add_argument('-p', '--password', dest='password', type=str, required=True)
    parser.add_argument('-d', '--database', dest='database', type=str, required=False)
    parser.add_argument('-t', '--node-type', dest='node_type', type=str, required=True)
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument('-l', '--user-list', dest='user_list', type=str)
    grp.add_argument('--user', dest='user', type=str)
    parser.add_argument('-debug', '--debug', action='store_true')

    args = parser.parse_args()
    if args.debug:
        logger.setLevel(logging.DEBUG)

    print('Client version: {0!s}'.format(client_version))

    device_id = None
    try:

        settings_file = args.settings_file_path
        if not os.path.isfile(settings_file):
            # settings file does not exist
            print('Unable to find file: {0!s}'.format(settings_file))

            # login new
            api = Client(
                args.username, args.password,
                on_login=lambda x: onlogin_callback(x, args.settings_file_path))
        else:
            with open(settings_file) as file_data:
                cached_settings = json.load(file_data, object_hook=from_json)
            print('Reusing settings: {0!s}'.format(settings_file))

            device_id = cached_settings.get('device_id')
            # reuse auth settings
            api = Client(
                args.username, args.password,
                settings=cached_settings)            

    except (ClientCookieExpiredError, ClientLoginRequiredError) as e:
        print('ClientCookieExpiredError/ClientLoginRequiredError: {0!s}'.format(e))

        # Login expired
        # Do relogin but use default ua, keys and such
        api = Client(
            args.username, args.password,
            device_id=device_id,
            on_login=lambda x: onlogin_callback(x, args.settings_file_path))

    except ClientLoginError as e:
        print('ClientLoginError {0!s}'.format(e))
        exit(9)
    except ClientError as e:
        print('ClientError {0!s} (Code: {1:d}, Response: {2!s})'.format(e.msg, e.code, e.error_response))
        exit(9)
    except Exception as e:
        print('Unexpected Exception: {0!s}'.format(e))
        exit(99)

    # Show when login expires
    cookie_expiry = api.cookie_jar.auth_expires
    print('Cookie Expiry: {0!s}'.format(datetime.datetime.fromtimestamp(cookie_expiry).strftime('%Y-%m-%dT%H:%M:%SZ')))

    user_list = []
    if args.user_list:
        with open(args.user_list) as user_file:
            user_list = [line.strip() for line in user_file.readlines() if len(line) > 0]
    elif args.user:
        user_list = [args.user]
    if len(user_list) == 0:
        logger.error("No users available")
    else:
        main(api, args.database or "ig_graph.db", args.node_type, user_list)


