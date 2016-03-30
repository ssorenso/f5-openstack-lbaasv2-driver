"""F5 Networks® LBaaSv2 Driver Implementation."""
# Copyright 2016 F5 Networks Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import sys

from oslo_config import cfg
from oslo_log import helpers as log_helpers
from oslo_log import log as logging
from oslo_utils import importutils

from neutron.common import constants as q_const

from f5lbaasdriver.v2.bigip import agent_rpc
from f5lbaasdriver.v2.bigip import plugin_rpc

LOG = logging.getLogger(__name__)

OPTS = [
    cfg.StrOpt(
        'f5_loadbalancer_pool_scheduler_driver_v2',
        default=(
            'f5lbaasdriver.v2.bigip.agent_scheduler.TenantScheduler'
        ),
        help=('Driver to use for scheduling '
              'pool to a default loadbalancer agent')
    ),
    cfg.StrOpt(
        'f5_loadbalancer_service_builder_v2',
        default=(
            'f5lbaasdriver.v2.bigip.service_builder.LBaaSv2ServiceBuilder'
        ),
        help=('Default class to use for building a service object.')
    )
]

cfg.CONF.register_opts(OPTS)


class F5DriverV2(object):
    """F5 Networks® LBaaSv2 Driver."""

    def __init__(self, plugin=None, env=None):
        """Driver initialization."""
        if not plugin:
            LOG.error('Required LBaaS Driver and Core Driver Missing')
            sys.exit(1)

        self.plugin = plugin
        self.env = env

        self.loadbalancer = LoadBalancerManager(self)
        self.listener = ListenerManager(self)
        self.pool = PoolManager(self)
        self.member = MemberManager(self)
        self.healthmonitor = HealthMonitorManager(self)

        # what scheduler to use for pool selection
        self.scheduler = importutils.import_object(
            cfg.CONF.f5_loadbalancer_pool_scheduler_driver_v2)

        self.service_builder = importutils.import_object(
            cfg.CONF.f5_loadbalancer_service_builder_v2, self)

        self.agent_rpc = agent_rpc.LBaaSv2AgentRPC(self)
        self.plugin_rpc = plugin_rpc.LBaaSv2PluginCallbacksRPC(self)

        # add this agent RPC to the neutron agent scheduler
        # mixins agent_notifiers dictionary for it's env
        self.plugin.agent_notifiers.update(
            {q_const.AGENT_TYPE_LOADBALANCER: self.agent_rpc})


class LoadBalancerManager(object):
    """LoadBalancerManager class handles Neutron LBaaS CRUD."""

    def __init__(self, driver):
        """Initialize Loadbalancer manager."""
        self.driver = driver

    @log_helpers.log_method_call
    def create(self, context, loadbalancer):
        """Create a loadbalancer."""
        driver = self.driver
        service = driver.service_builder.build(context, loadbalancer)
        agent = driver.scheduler.schedule(
            driver.plugin,
            context,
            loadbalancer.id,
            driver.env
        )
        driver.agent_rpc.create_loadbalancer(
            context,
            loadbalancer.to_api_dict(),
            service,
            agent['host']
        )

    @log_helpers.log_method_call
    def update(self, context, old_loadbalancer, loadbalancer):
        """Update a loadbalancer."""
        driver = self.driver
        service = driver.service_builder.build(context, loadbalancer)
        agent = driver.scheduler.schedule(
            driver.plugin,
            context,
            loadbalancer.id,
            driver.env
        )
        driver.agent_rpc.update_loadbalancer(
            context,
            old_loadbalancer.to_api_dict(),
            loadbalancer.to_api_dict(),
            service,
            agent['host']
        )

    @log_helpers.log_method_call
    def delete(self, context, loadbalancer):
        """Delete a loadbalancer."""
        driver = self.driver
        service = driver.service_builder.build(context, loadbalancer)
        agent = driver.scheduler.schedule(
            driver.plugin,
            context,
            loadbalancer.id,
            driver.env
        )
        driver.agent_rpc.delete_loadbalancer(
            context,
            loadbalancer.to_api_dict(),
            service,
            agent['host']
        )

    @log_helpers.log_method_call
    def refresh(self, context, loadbalancer):
        """Refresh a loadbalancer."""
        pass

    @log_helpers.log_method_call
    def stats(self, context, loadbalancer):
        """Get loadbalancer statistics."""
        pass


class ListenerManager(object):
    """ListenerManager class handles Neutron LBaaS listener CRUD."""

    def __init__(self, driver):
        """Initialize a ListenerManager object."""
        self.driver = driver

    @log_helpers.log_method_call
    def create(self, context, listener):
        """Create a listener."""
        driver = self.driver
        if listener.attached_to_loadbalancer():
            loadbalancer = listener.loadbalancer
            service = driver.service_builder.build(context, loadbalancer)
            agent = driver.scheduler.schedule(
                driver.plugin,
                context,
                loadbalancer.id,
                driver.env
            )
            driver.agent_rpc.create_listener(
                context,
                listener.to_dict(loadbalancer=False, default_pool=False),
                service,
                agent['host']
            )

    @log_helpers.log_method_call
    def update(self, context, old_listener, listener):
        """Update a listener."""
        driver = self.driver
        if listener.attached_to_loadbalancer():
            loadbalancer = listener.loadbalancer
            service = driver.service_builder.build(context, loadbalancer)
            agent = driver.scheduler.schedule(
                driver.plugin,
                context,
                loadbalancer.id,
                driver.env
            )
            driver.agent_rpc.update_listener(
                context,
                old_listener.to_dict(loadbalancer=False, default_pool=False),
                listener.to_dict(loadbalancer=False, default_pool=False),
                service,
                agent['host']
            )

    @log_helpers.log_method_call
    def delete(self, context, listener):
        """Delete a listener."""
        driver = self.driver
        if listener.attached_to_loadbalancer():
            loadbalancer = listener.loadbalancer
            service = driver.service_builder.build(context, loadbalancer)
            agent = driver.scheduler.schedule(
                driver.plugin,
                context,
                loadbalancer.id,
                driver.env
            )
            driver.agent_rpc.delete_listener(
                context,
                listener.to_dict(loadbalancer=False, default_pool=False),
                service,
                agent['host']
            )


class PoolManager(object):
    """PoolManager class handles Neutron LBaaS pool CRUD."""

    def __init__(self, driver):
        """Initialize a PoolManager object."""
        self.driver = driver

    def _get_pool_dict(self, pool):
        pool_dict = pool.to_api_dict()
        pool_dict['provisioning_status'] = pool.provisioning_status
        pool_dict['operating_status'] = pool.operating_status
        return pool_dict

    @log_helpers.log_method_call
    def create(self, context, pool):
        """Create a pool."""
        driver = self.driver
        if pool.attached_to_loadbalancer():
            loadbalancer = pool.listener.loadbalancer
            service = driver.service_builder.build(context, loadbalancer)
            agent = driver.scheduler.schedule(
                driver.plugin,
                context,
                loadbalancer.id,
                driver.env
            )
            driver.agent_rpc.create_pool(
                context,
                self._get_pool_dict(pool),
                service,
                agent['host']
            )

    @log_helpers.log_method_call
    def update(self, context, old_pool, pool):
        """Update a pool."""
        driver = self.driver
        if pool.attached_to_loadbalancer():
            loadbalancer = pool.listener.loadbalancer
            service = driver.service_builder.build(context, loadbalancer)
            agent = driver.scheduler.schedule(
                driver.plugin,
                context,
                loadbalancer.id,
                driver.env
            )
            driver.agent_rpc.update_pool(
                context,
                self._get_pool_dict(old_pool),
                self._get_pool_dict(pool),
                service,
                agent['host']
            )

    @log_helpers.log_method_call
    def delete(self, context, pool):
        """Delete a pool."""
        driver = self.driver
        if pool.attached_to_loadbalancer():
            loadbalancer = pool.listener.loadbalancer
            service = driver.service_builder.build(context, loadbalancer)
            agent = driver.scheduler.schedule(
                driver.plugin,
                context,
                loadbalancer.id,
                driver.env
            )
            driver.agent_rpc.delete_pool(
                context,
                self._get_pool_dict(pool),
                service,
                agent['host']
            )


class MemberManager(object):
    """MemberManager class handles Neutron LBaaS pool member CRUD."""

    def __init__(self, driver):
        """Initialize a MemberManager object."""
        self.driver = driver

    @log_helpers.log_method_call
    def create(self, context, member):
        """Create a member."""
        driver = self.driver
        if member.attached_to_loadbalancer():
            loadbalancer = member.pool.listener.loadbalancer
            service = driver.service_builder.build(context, loadbalancer)
            agent = driver.scheduler.schedule(
                driver.plugin,
                context,
                loadbalancer.id,
                driver.env
            )
            driver.agent_rpc.create_member(
                context,
                member.to_dict(pool=False),
                service,
                agent['host']
            )
        else:
            LOG.error("member not attached to loadbalancer")

    @log_helpers.log_method_call
    def update(self, context, old_member, member):
        """Update a member."""
        driver = self.driver
        if member.attached_to_loadbalancer():
            loadbalancer = member.pool.listener.loadbalancer
            service = driver.service_builder.build(context, loadbalancer)
            agent = driver.scheduler.schedule(
                driver.plugin,
                context,
                loadbalancer.id,
                driver.env
            )
            driver.agent_rpc.update_member(
                context,
                old_member.to_dict(pool=False),
                member.to_dict(pool=False),
                service,
                agent['host']
            )

    @log_helpers.log_method_call
    def delete(self, context, member):
        """Delete a member."""
        driver = self.driver
        if member.attached_to_loadbalancer():
            loadbalancer = member.pool.listener.loadbalancer
            service = driver.service_builder.build(context, loadbalancer)
            agent = driver.scheduler.schedule(
                driver.plugin,
                context,
                loadbalancer.id,
                driver.env
            )
            driver.agent_rpc.delete_member(
                context,
                member.to_dict(pool=False),
                service,
                agent['host']
            )


class HealthMonitorManager(object):
    """HealthMonitorManager class handles Neutron LBaaS monitor CRUD."""

    def __init__(self, driver):
        """Initialize a HealthMonitorManager object."""
        self.driver = driver

    @log_helpers.log_method_call
    def create(self, context, health_monitor):
        """Create a health monitor."""
        driver = self.driver
        if health_monitor.attached_to_loadbalancer():
            loadbalancer = health_monitor.pool.listener.loadbalancer
            service = driver.service_builder.build(context, loadbalancer)
            agent = driver.scheduler.schedule(
                driver.plugin,
                context,
                loadbalancer.id,
                driver.env
            )
            driver.agent_rpc.create_health_monitor(
                context,
                health_monitor.to_dict(pool=False),
                service,
                agent['host']
            )
        else:
            LOG.error("health monitor not attached to loadbalancer")

    @log_helpers.log_method_call
    def update(self, context, old_health_monitor, health_monitor):
        """Update a health monitor."""
        driver = self.driver
        if health_monitor.attached_to_loadbalancer():
            loadbalancer = health_monitor.pool.listener.loadbalancer
            service = driver.service_builder.build(context, loadbalancer)
            agent = driver.scheduler.schedule(
                driver.plugin,
                context,
                loadbalancer.id,
                driver.env
            )
            driver.agent_rpc.update_health_monitor(
                context,
                old_health_monitor.to_dict(pool=False),
                health_monitor.to_dict(pool=False),
                service,
                agent['host']
            )

    @log_helpers.log_method_call
    def delete(self, context, health_monitor):
        """Delete a health monitor."""
        driver = self.driver
        if health_monitor.attached_to_loadbalancer():
            loadbalancer = health_monitor.pool.listener.loadbalancer
            service = driver.service_builder.build(context, loadbalancer)
            agent = driver.scheduler.schedule(
                driver.plugin,
                context,
                loadbalancer.id,
                driver.env
            )
            driver.agent_rpc.delete_health_monitor(
                context,
                health_monitor.to_dict(pool=False),
                service,
                agent['host']
            )
