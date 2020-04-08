"""Models used by the maintenance NApp,

This module define models for the maintenance window itself and the
scheduler.
"""
from uuid import uuid4
import datetime

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import JobLookupError
from pytz import utc
from kytos.core import log, KytosEvent
from kytos.core.interface import TAG, UNI
from kytos.core.link import Link

TIME_FMT = "%Y-%m-%dT%H:%M:%S%z"


class MaintenanceWindow:
    """Class to store a maintenance window."""

    def __init__(self, start, end, controller, items=None, mw_id=None):
        """Create an instance of MaintenanceWindow.

        Args:
            start(datetime): when the maintenance will begin
            end(datetime): when the maintenance will finish
            items: list of items that will be maintained;
                each item can be either a switch, a link or a client interface
        """
        if items is None:
            items = list()
        self.id = mw_id if mw_id else uuid4().hex
        self.start = start
        self.end = end
        self.items = items
        self.controller = controller

    def as_dict(self):
        """Return this maintenance window as a dictionary."""
        mw_dict = dict()
        mw_dict['id'] = self.id
        mw_dict['start'] = self.start.strftime(TIME_FMT)
        mw_dict['end'] = self.end.strftime(TIME_FMT)
        mw_dict['items'] = []
        for i in self.items:
            try:
                mw_dict['items'].append(i.as_dict())
            except (AttributeError, TypeError):
                mw_dict['items'].append(i)
        return mw_dict

    @classmethod
    def from_dict(cls, mw_dict, controller):
        """Create a maintenance window from a dictionary of attributes."""
        mw_id = mw_dict.get('id')

        start = datetime.datetime.strptime(mw_dict['start'], TIME_FMT).astimezone(pytz.utc)
        end = datetime.datetime.strptime(mw_dict['end'], TIME_FMT).astimezone(pytz.utc)
        items = list()
        for i in mw_dict['items']:
            try:
                item = cls.uni_from_dict(i, controller)
            except KeyError:
                item = cls.link_from_dict(i, controller)
            except TypeError:
                item = i
            if item is None:
                return None
            items.append(item)
        return cls(start, end, controller, items, mw_id)

    def update(self, mw_dict, controller):
        """Update a maintenance window with the data from a dictionary."""
        if 'start' in mw_dict:
            self.start = datetime.datetime.strptime(mw_dict['start'], TIME_FMT).astimezone(pytz.utc)
        if 'end' in mw_dict:
            self.end = datetime.datetime.strptime(mw_dict['end'], TIME_FMT).astimezone(pytz.utc)
        if 'items' in mw_dict:
            items = list()
            for i in mw_dict['items']:
                try:
                    item = self.uni_from_dict(i, controller)
                except KeyError:
                    item = self.link_from_dict(i, controller)
                except TypeError:
                    item = i
                if item:
                    items.append(item)
            self.items = items

    @staticmethod
    def intf_from_dict(intf_id, controller):
        """Get the Interface instance with intf_id."""
        intf = controller.get_interface_by_id(intf_id)
        return intf

    @staticmethod
    def uni_from_dict(uni_dict, controller):
        """Create UNI instance from a dictionary."""
        intf = MaintenanceWindow.intf_from_dict(uni_dict['interface_id'],
                                                controller)
        tag = TAG.from_dict(uni_dict['tag'])
        if intf and tag:
            return UNI(intf, tag)
        return None

    @staticmethod
    def link_from_dict(link_dict, controller):
        """Create a link instance from a dictionary."""
        endpoint_a = controller.get_interface_by_id(
            link_dict['endpoint_a']['id'])
        endpoint_b = controller.get_interface_by_id(
            link_dict['endpoint_b']['id'])

        link = Link(endpoint_a, endpoint_b)
        if 'metadata' in link_dict:
            link.extend_metadata(link_dict['metadata'])
        s_vlan = link.get_metadata('s_vlan')
        if s_vlan:
            tag = TAG.from_dict(s_vlan)
            link.update_metadata('s_vlan', tag)
        return link

    def start_mw(self):
        """Actions taken when a maintenance window starts."""
        pass

    def end_mw(self):
        """Actions taken when a maintenance window finishes."""
        pass


class Scheduler:
    """Scheduler for a maintenance window."""

    def __init__(self):
        """Initialize a new scheduler."""
        self.scheduler = BackgroundScheduler(timezone=utc)
        self.scheduler.start()

    def add(self, mw):
        """Add jobs to start and end a maintenance window."""
        self.scheduler.add_job(mw.start_mw, 'date', id=f'{mw.id}-start',
                               run_date=mw.start)
        self.scheduler.add_job(mw.end_mw, 'date', id=f'{mw.id}-end',
                               run_date=mw.end)

    def remove(self, mw):
        """Remove jobs that start and end a maintenance window."""
        try:
            self.scheduler.remove_job(f'{mw.id}-start')
        except JobLookupError:
            log.info(f'Job to start {mw.id} already removed.')
        try:
            self.scheduler.remove_job(f'{mw.id}-end')
        except JobLookupError:
            log.info(f'Job to end {mw.id} already removed.')