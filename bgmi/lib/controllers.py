# coding=utf-8
import os
import time

from bgmi.config import write_config, MAX_PAGE
from bgmi.lib.download import download_prepare
from bgmi.lib.fetch import data_source
from bgmi.lib.models import Filter, Subtitle, Download, STATUS_FOLLOWED, STATUS_UPDATED, STATUS_NOT_DOWNLOAD, FOLLOWED_STATUS, Followed, Bangumi, model_to_dict, STATUS_DELETED
from bgmi.script import ScriptRunner
from bgmi.utils import print_info, normalize_path, print_warning, print_success, print_error, GREEN, COLOR_END, logger


def add(name, episode=None):
    """
    ret.name :str
    """
    # action add
    # add bangumi by a list of bangumi name
    # result = {}
    logger.debug('add name: {} episode: {}'.format(name, episode))
    if not Bangumi.get_updating_bangumi():
        data_source.fetch(save=True, group_by_weekday=False)

    try:
        bangumi_obj = Bangumi.get(name=name)
    except Bangumi.DoesNotExist:
        result = {'status': 'error',
                  'message': '{0} not found, please check the name'.format(name)}
        return result

    followed_obj, this_obj_created = Followed.get_or_create(bangumi_name=bangumi_obj.name,
                                                            defaults={'status': STATUS_FOLLOWED})
    if not this_obj_created:
        if followed_obj.status == STATUS_FOLLOWED:
            result = {'status': 'warning', 'message': '{0} already followed'.format(bangumi_obj.name)}
            return result
        else:
            followed_obj.status = STATUS_FOLLOWED
            followed_obj.save()

    Filter.get_or_create(bangumi_name=name)

    bangumi_data, _ = data_source.get_maximum_episode(bangumi_obj, subtitle=False, max_page=MAX_PAGE)
    followed_obj.episode = bangumi_data['episode'] if episode is None else episode
    followed_obj.save()
    result = {'status': 'success', 'message': '{0} has been followed'.format(bangumi_obj.name)}
    logger.debug(result)
    return result


def filter_(name, subtitle=None, include=None, exclude=None, regex=None, data_source=None):
    def check_input(filter_obj, field, user_input, usable_list):
        if user_input == '':
            setattr(filter_obj, field, None)
            return True
        string = [s.strip() for s in user_input.split(',') if s.strip()]
        string_list = []
        for s in string:
            if s in usable_list:
                string_list.append(s)
            else:
                return False
        string = ', '.join(string_list)
        setattr(filter_obj, field, string)
        return True

    result = {'status': 'success', 'message': ''}
    try:
        bangumi_obj = Bangumi.get(name=name)  # type: Bangumi
    except Bangumi.DoesNotExist:
        result['status'] = 'error'
        result['message'] = 'Bangumi {0} does not exist.'.format(name)
        return result

    try:
        Followed.get(bangumi_name=bangumi_obj.name)
    except Followed.DoesNotExist as exc:
        result['status'] = 'error'
        result['message'] = 'Bangumi {name} has not subscribed, try \'bgmi add "{name}"\'.' \
            .format(name=bangumi_obj.name)
        return result

    followed_filter_obj, _ = Filter.get_or_create(bangumi_name=name)
    subtitle_list = list(map(lambda s: s['name'], Subtitle.get_subtitle_of_bangumi(bangumi_obj)))
    if subtitle is not None:
        if not check_input(followed_filter_obj, 'subtitle', subtitle, subtitle_list):
            result['status'] = 'error'
            result['message'] = '{} is not valid subtitle group'.format(subtitle)
            return result

    if include is not None:
        followed_filter_obj.include = include

    if exclude is not None:
        followed_filter_obj.exclude = exclude

    if regex is not None:
        followed_filter_obj.regex = regex

    if data_source is not None:
        if not check_input(followed_filter_obj, 'data_source', data_source, bangumi_obj.data_source.keys()):
            result['status'] = 'error'
            result['message'] = '{} is not valid data source'.format(data_source)
            return result

    followed_filter_obj.save()

    data_source_list = list(bangumi_obj.data_source.keys())
    result['data'] = {
        'name'          : name,
        'subtitle_group': subtitle_list,
        'data_source'   : data_source_list,
        'followed'      : followed_filter_obj.subtitle.split(', ') if followed_filter_obj.subtitle else [],
        'include'       : followed_filter_obj.include,
        'exclude'       : followed_filter_obj.exclude,
        'regex'         : followed_filter_obj.regex,
    }
    logger.debug(result)
    return result


def delete(name='', clear_all=False, batch=False):
    """
    :param name:
    :type name: unicode
    :param clear_all:
    :type clear_all: bool
    :param batch:
    :type batch: bool
    :return:
    """
    # action delete
    # just delete subscribed bangumi or clear all the subscribed bangumi
    result = {}
    logger.debug('delete {}'.format(name))
    if clear_all:
        if Followed.delete_followed(batch=batch):
            result['status'] = "warning"
            result['message'] = 'all subscriptions have been deleted'
        else:
            print_error('user canceled')
    elif name:
        try:
            followed = Followed.get(bangumi_name=name)
            followed.status = STATUS_DELETED
            followed.save()
            result['status'] = 'warning'
            result['message'] = 'Bangumi {} has been deleted'.format(name)
        except Followed.DoesNotExist:
            result['status'] = 'error'
            result['message'] = 'Bangumi %s does not exist' % name
    else:
        result['status'] = 'warning'
        result['message'] = 'Nothing has been done.'
    logger.debug(result)
    return result


def cal(force_update=False, save=False):
    logger.debug('cal force_update: {} save: {}'.format(force_update, save))
    weekly_list = data_source.bangumi_calendar(force_update=force_update, save=save)
    runner = ScriptRunner()
    patch_list = runner.get_models_dict()
    for i in patch_list:
        weekly_list[i['update_time'].lower()].append(i)
    logger.debug(weekly_list)

    # for web api, return all subtitle group info
    r = weekly_list
    for day, value in weekly_list.items():
        for index, bangumi in enumerate(value):
            bangumi['cover'] = normalize_path(bangumi['cover'])
            subtitle_group = Subtitle.get_subtitle_from_data_source_dict(bangumi['data_source'])
            r[day][index]['subtitle_group'] = subtitle_group
    logger.debug(r)
    return r


def download(name, title, episode, download_url):
    my_dict = {
        'name': name,
        'title': title,
        'episode': episode,
        'download': download_url,
    }
    download_prepare(my_dict)


def mark(name, episode):
    """

    :param name: name of the bangumi you want to mark
    :type name: str
    :param episode: bangumi episode you want to mark
    :type episode: int
    :return: result
    :rtype: dict[status: str,message: str]
    """
    result = {}
    try:
        followed_obj = Followed.get(bangumi_name=name)
    except Followed.DoesNotExist:
        runner = ScriptRunner()
        followed_obj = runner.get_model(name)
        if not followed_obj:
            result['status'] = 'error'
            result['message'] = 'Subscribe or Script <{}> does not exist.'.format(name)
            return result

    if episode is not None:
        followed_obj.episode = episode
        followed_obj.save()
        result['status'] = 'success'
        result['message'] = '{} has been mark as episode: {}'.format(name, episode)
    else:  # episode is None
        result['status'] = 'info'
        result['message'] = '{}, episode: {}'.format(name, followed_obj.episode)
    return result


def search(keyword, count=MAX_PAGE, regex=None, dupe=False, min_episode=None, max_episode=None):
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = 3
    try:
        data = data_source.search_by_keyword(keyword, count=count)
        data = data_source.utils.filter_keyword(data, regex=regex)
        if min_episode is not None:
            data = [x for x in data if x['episode'] >= min_episode]
        if max_episode is not None:
            data = [x for x in data if x['episode'] <= max_episode]
        # for i in data:
        #     if i['episode'] >= min_episode:
        #         r.append(i)

        if not dupe:
            data = data_source.utils.remove_duplicated_bangumi(data)
        data.sort(key=lambda x: x['episode'])
        return {
            'status': 'success',
            'message': '',
            'options': dict(keyword=keyword,
                            count=count,
                            regex=regex,
                            dupe=dupe,
                            min_episode=min_episode,
                            max_episode=max_episode),
            'data': data}
    except Exception as e:
        if os.environ.get('DEBUG'):
            raise e
        return {
            'status': 'error',
            'message': str(e),
            'options': dict(keyword=keyword,
                            count=count,
                            regex=regex,
                            dupe=dupe,
                            min_episode=min_episode,
                            max_episode=max_episode),
            'data': []}


def config(name=None, value=None):
    r = write_config(name, value)
    if name == 'ADMIN_TOKEN':
        r['message'] = 'you need to restart your bgmi_http to make new token work'
    return r


def update(name, download=None, not_ignore=False):
    logger.debug('updating bangumi info with args: download: {}'.format(download))
    result = {'status': 'info', 'message': '', 'data': {'updated': [], 'downloaded': []}}

    ignore = not bool(not_ignore)
    print_info('marking bangumi status ...')
    now = int(time.time())

    for i in Followed.get_all_followed():
        if i['updated_time'] and int(i['updated_time'] + 60 * 60 * 24) < now:
            followed_obj = Followed.get(bangumi_name=i['bangumi_name'])
            followed_obj.status = STATUS_FOLLOWED
            followed_obj.save()

    for script in ScriptRunner().scripts:
        obj = script.Model().obj
        if obj.updated_time and int(obj.updated_time + 60 * 60 * 24) < now:
            obj.status = STATUS_FOLLOWED
            obj.save()

    print_info('updating bangumi data ...')
    data_source.fetch(save=True, group_by_weekday=False)
    print_info('updating subscriptions ...')
    download_queue = []

    if download:
        if not name:
            print_warning('No specified bangumi, ignore `--download` option')
        if len(name) > 1:
            print_warning('Multiple specified bangumi, ignore `--download` option')

    if not name:
        updated_bangumi_obj = Followed.get_all_followed()
    else:
        updated_bangumi_obj = []
        for i in name:
            try:
                f = Followed.get(bangumi_name=i)
                f = model_to_dict(f)
                updated_bangumi_obj.append(f)
            except Followed.DoesNotExist:
                pass

    runner = ScriptRunner()
    script_download_queue = runner.run()

    for subscribe in updated_bangumi_obj:
        print_info('fetching %s ...' % subscribe['bangumi_name'])
        try:
            bangumi_obj = Bangumi.get(name=subscribe['bangumi_name'])
        except Bangumi.DoesNotExist:
            print_error('Bangumi<{0}> does not exists.'.format(subscribe['bangumi_name']),
                        exit_=False)
            continue
        try:
            followed_obj = Followed.get(bangumi_name=subscribe['bangumi_name'])
        except Followed.DoesNotExist:
            print_error('Bangumi<{0}> is not followed.'.format(subscribe['bangumi_name']),
                        exit_=False)
            continue

        episode, all_episode_data = data_source.get_maximum_episode(bangumi=bangumi_obj, ignore_old_row=ignore,
                                                                    max_page=1)

        if (episode.get('episode') > subscribe['episode']) or (len(name) == 1 and download):
            if len(name) == 1 and download:
                episode_range = download
            else:
                episode_range = range(
                    subscribe['episode'] + 1, episode.get('episode', 0) + 1)
                print_success('%s updated, episode: %d' %
                              (subscribe['bangumi_name'], episode['episode']))
                followed_obj.episode = episode['episode']
                followed_obj.status = STATUS_UPDATED
                followed_obj.updated_time = int(time.time())
                followed_obj.save()
                result['data']['updated'].append({'bangumi': subscribe['bangumi_name'],
                                                  'episode': episode['episode']})

            for i in episode_range:
                for epi in all_episode_data:
                    if epi['episode'] == i:
                        download_queue.append(epi)
                        break

    if download is not None:
        result['data']['downloaded'] = download_queue
        download_prepare(download_queue)
        download_prepare(script_download_queue)
        print_info('Re-downloading ...')
        download_prepare(Download.get_all_downloads(
            status=STATUS_NOT_DOWNLOAD))

    return result


def status_(name, status=STATUS_DELETED):
    result = {'status': 'success', 'message': ''}

    if not status in FOLLOWED_STATUS or not status:
        result['status'] = 'error'
        result['message'] = 'Invalid status: {0}'.format(status)
        return result

    status = int(status)
    try:
        followed_obj = Followed.get(bangumi_name=name)
    except Followed.DoesNotExist:
        result['status'] = 'error'
        result['message'] = 'Followed<{0}> does not exists'.format(name)
        return result

    followed_obj.status = status
    followed_obj.save()
    result['message'] = 'Followed<{0}> has been marked as status {1}'.format(name, status)
    return result


def list_():
    result = {}
    weekday_order = Bangumi.week
    followed_bangumi = data_source.followed_bangumi()

    script_bangumi = ScriptRunner().get_models_dict()

    if not followed_bangumi and not script_bangumi:
        result['status'] = 'warning'
        result['message'] = 'you have not subscribed any bangumi'
        return result

    for i in script_bangumi:
        i['subtitle_group'] = [{'name': '<BGmi Script>'}]
        followed_bangumi[i['update_time'].lower()].append(i)

    result['status'] = 'info'
    result['message'] = ''
    for index, weekday in enumerate(weekday_order):
        if followed_bangumi[weekday.lower()]:
            result['message'] += '%s%s. %s' % (GREEN, weekday, COLOR_END)
            for i, bangumi in enumerate(followed_bangumi[weekday.lower()]):
                if bangumi['status'] in (STATUS_UPDATED, STATUS_FOLLOWED) and 'episode' in bangumi:
                    bangumi['name'] = '%s(%d)' % (
                        bangumi['name'], bangumi['episode'])
                if i > 0:
                    result['message'] += ' ' * 5
                f = map(lambda x: x['name'], bangumi['subtitle_group'])
                result['message'] += '%s: %s\n' % (bangumi['name'], ', '.join(f) if f else '<None>')

    return result


if __name__ == '__main__':
    filter_('海贼王', )
