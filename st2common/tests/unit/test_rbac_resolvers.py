# Licensed to the StackStorm, Inc ('StackStorm') under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from oslo_config import cfg

from st2common.services import rbac as rbac_services
from st2common.rbac.types import PermissionType
from st2common.rbac.types import ResourceType
from st2common.rbac.types import SystemRole
from st2common.persistence.auth import User
from st2common.persistence.rbac import Role
from st2common.persistence.rbac import UserRoleAssignment
from st2common.persistence.rbac import PermissionGrant
from st2common.persistence.pack import Pack
from st2common.persistence.sensor import SensorType
from st2common.persistence.action import Action
from st2common.persistence.rule import Rule
from st2common.models.db.auth import UserDB
from st2common.models.db.rbac import RoleDB
from st2common.models.db.rbac import UserRoleAssignmentDB
from st2common.models.db.rbac import PermissionGrantDB
from st2common.models.db.pack import PackDB
from st2common.models.db.sensor import SensorTypeDB
from st2common.models.db.action import ActionDB
from st2common.models.db.rule import RuleDB
from st2common.rbac.resolvers import SensorPermissionsResolver
from st2common.rbac.resolvers import ActionPermissionsResolver
from st2common.rbac.resolvers import RulePermissionsResolver
from st2common.rbac.migrations import insert_system_roles
from st2tests.base import CleanDbTestCase

__all__ = [
    'SensorPermissionsResolverTestCase',
    'ActionPermissionsResolverTestCase',
    'RulePermissionsResolverTestCase'
]


class BasePermissionsResolverTestCase(CleanDbTestCase):
    def setUp(self):
        super(BasePermissionsResolverTestCase, self).setUp()

        # Make sure RBAC is enabeld
        cfg.CONF.set_override(name='enable', override=True, group='rbac')

        self.users = {}
        self.roles = {}
        self.resources = {}

        # Run role "migrations"
        insert_system_roles()

        # Insert common mock objects
        self._insert_common_mocks()

    def _insert_common_mocks(self):
        self._insert_common_mock_users()
        self._insert_common_mock_resources()
        self._insert_common_mock_roles()
        self._insert_common_mock_role_assignments()

    def _insert_common_mock_users(self):
        # Insert common mock users
        user_1_db = UserDB(name='admin')
        user_1_db = User.add_or_update(user_1_db)
        self.users['admin'] = user_1_db

        user_2_db = UserDB(name='observer')
        user_2_db = User.add_or_update(user_2_db)
        self.users['observer'] = user_2_db

        user_3_db = UserDB(name='no_roles')
        user_3_db = User.add_or_update(user_3_db)
        self.users['no_roles'] = user_3_db

        user_4_db = UserDB(name='1_custom_role_no_permissions')
        user_4_db = User.add_or_update(user_4_db)
        self.users['1_custom_role_no_permissions'] = user_4_db

        user_5_db = UserDB(name='1_role_pack_grant')
        user_5_db = User.add_or_update(user_5_db)
        self.users['custom_role_pack_grant'] = user_5_db

    def _insert_common_mock_resources(self):
        pack_1_db = PackDB(name='test_pack_1', ref='test_pack_1', description='',
                           version='0.1.0', author='foo', email='test@example.com')
        pack_1_db = Pack.add_or_update(pack_1_db)
        self.resources['pack_1'] = pack_1_db

        pack_2_db = PackDB(name='test_pack_2', ref='test_pack_2', description='',
                           version='0.1.0', author='foo', email='test@example.com')
        pack_2_db = Pack.add_or_update(pack_2_db)
        self.resources['pack_2'] = pack_2_db

    def _insert_common_mock_roles(self):
        # Insert common mock roles
        admin_role_db = rbac_services.get_role_by_name(name=SystemRole.ADMIN)
        observer_role_db = rbac_services.get_role_by_name(name=SystemRole.OBSERVER)
        self.roles['admin_role'] = admin_role_db
        self.roles['observer_role'] = observer_role_db

        # Custom role 1 - no grants
        role_1_db = rbac_services.create_role(name='custom_role_1')
        self.roles['custom_role_1'] = role_1_db

        # Custom role 2 - one grant on pack_1
        # "pack_create" on pack_1
        grant_db = PermissionGrantDB(resource_uid=self.resources['pack_1'].get_uid(),
                                     resource_type=ResourceType.PACK,
                                     permission_types=[PermissionType.PACK_CREATE])
        grant_db = PermissionGrant.add_or_update(grant_db)
        permission_grants = [str(grant_db.id)]
        role_3_db = RoleDB(name='custom_role_pack_grant', permission_grants=permission_grants)
        role_3_db = Role.add_or_update(role_3_db)
        self.roles['custom_role_pack_grant'] = role_3_db

    def _insert_common_mock_role_assignments(self):
        # Insert common mock role assignments
        role_assignment_admin = UserRoleAssignmentDB(user=self.users['admin'].name,
                                                     role=self.roles['admin_role'].name)
        role_assignment_admin = UserRoleAssignment.add_or_update(role_assignment_admin)
        role_assignment_observer = UserRoleAssignmentDB(user=self.users['observer'].name,
                                                        role=self.roles['observer_role'].name)
        role_assignment_observer = UserRoleAssignment.add_or_update(role_assignment_observer)

        user_db = self.users['1_custom_role_no_permissions']
        role_assignment_db = UserRoleAssignmentDB(user=user_db.name,
                                                  role=self.roles['custom_role_1'].name)
        UserRoleAssignment.add_or_update(role_assignment_db)

        user_db = self.users['custom_role_pack_grant']
        role_assignment_db = UserRoleAssignmentDB(user=user_db.name,
                                                  role=self.roles['custom_role_pack_grant'].name)
        UserRoleAssignment.add_or_update(role_assignment_db)


class SensorPermissionsResolverTestCase(BasePermissionsResolverTestCase):
    def setUp(self):
        super(SensorPermissionsResolverTestCase, self).setUp()

        # Create some mock users
        user_6_db = UserDB(name='1_role_sensor_pack_grant')
        user_6_db = User.add_or_update(user_6_db)
        self.users['custom_role_sensor_pack_grant'] = user_6_db

        user_7_db = UserDB(name='1_role_sensor_grant')
        user_7_db = User.add_or_update(user_7_db)
        self.users['custom_role_sensor_grant'] = user_7_db

        # Create some mock resources on which permissions can be granted
        sensor_1_db = SensorTypeDB(pack='test_pack_1', name='sensor1')
        sensor_1_db = SensorType.add_or_update(sensor_1_db)
        self.resources['sensor_1'] = sensor_1_db

        sensor_2_db = SensorTypeDB(pack='test_pack_1', name='sensor2')
        sensor_2_db = SensorType.add_or_update(sensor_2_db)
        self.resources['sensor_2'] = sensor_2_db

        sensor_3_db = SensorTypeDB(pack='test_pack_2', name='sensor3')
        sensor_3_db = SensorType.add_or_update(sensor_3_db)
        self.resources['sensor_3'] = sensor_3_db

        # Create some mock roles with associated permission grants
        # Custom role 2 - one grant on parent pack
        # "sensor_view" on pack_1
        grant_db = PermissionGrantDB(resource_uid=self.resources['pack_1'].get_uid(),
                                     resource_type=ResourceType.PACK,
                                     permission_types=[PermissionType.SENSOR_VIEW])
        grant_db = PermissionGrant.add_or_update(grant_db)
        permission_grants = [str(grant_db.id)]
        role_3_db = RoleDB(name='custom_role_sensor_pack_grant',
                           permission_grants=permission_grants)
        role_3_db = Role.add_or_update(role_3_db)
        self.roles['custom_role_sensor_pack_grant'] = role_3_db

        # Custom role 4 - one grant on pack
        # "sensor_view on sensor_3
        grant_db = PermissionGrantDB(resource_uid=self.resources['sensor_3'].get_uid(),
                                     resource_type=ResourceType.SENSOR,
                                     permission_types=[PermissionType.SENSOR_VIEW])
        grant_db = PermissionGrant.add_or_update(grant_db)
        permission_grants = [str(grant_db.id)]
        role_4_db = RoleDB(name='custom_role_sensor_grant', permission_grants=permission_grants)
        role_4_db = Role.add_or_update(role_4_db)
        self.roles['custom_role_sensor_grant'] = role_4_db

        # Create some mock role assignments
        user_db = self.users['custom_role_sensor_pack_grant']
        role_assignment_db = UserRoleAssignmentDB(
            user=user_db.name,
            role=self.roles['custom_role_sensor_pack_grant'].name)
        UserRoleAssignment.add_or_update(role_assignment_db)

        user_db = self.users['custom_role_sensor_grant']
        role_assignment_db = UserRoleAssignmentDB(user=user_db.name,
                                                  role=self.roles['custom_role_sensor_grant'].name)
        UserRoleAssignment.add_or_update(role_assignment_db)

    def test_user_has_resource_permission(self):
        resolver = SensorPermissionsResolver()

        # Admin user, should always return true
        resource_db = self.resources['sensor_1']
        user_db = self.users['admin']
        self.assertTrue(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=resource_db,
            permission_type=PermissionType.SENSOR_ALL))
        self.assertTrue(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=resource_db,
            permission_type=PermissionType.SENSOR_VIEW))

        # Observer, should always return true for VIEW permission
        user_db = self.users['observer']
        self.assertTrue(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['sensor_1'],
            permission_type=PermissionType.SENSOR_VIEW))
        self.assertTrue(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['sensor_2'],
            permission_type=PermissionType.SENSOR_VIEW))

        # No roles, should return false for everything
        user_db = self.users['no_roles']
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['sensor_1'],
            permission_type=PermissionType.SENSOR_VIEW))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['sensor_2'],
            permission_type=PermissionType.SENSOR_ALL))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['sensor_3'],
            permission_type=PermissionType.SENSOR_VIEW))

        # Custom role with no permission grants, should return false for everything
        user_db = self.users['1_custom_role_no_permissions']
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['sensor_1'],
            permission_type=PermissionType.SENSOR_VIEW))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['sensor_2'],
            permission_type=PermissionType.SENSOR_ALL))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['sensor_3'],
            permission_type=PermissionType.SENSOR_VIEW))

        # Custom role with unrelated permission grant to parent pack
        user_db = self.users['custom_role_pack_grant']
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['sensor_1'],
            permission_type=PermissionType.SENSOR_VIEW))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['sensor_2'],
            permission_type=PermissionType.SENSOR_ALL))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['sensor_3'],
            permission_type=PermissionType.SENSOR_VIEW))

        # Custom role with with grant on the parent pack
        user_db = self.users['custom_role_sensor_pack_grant']
        self.assertTrue(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['sensor_1'],
            permission_type=PermissionType.SENSOR_VIEW))
        self.assertTrue(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['sensor_2'],
            permission_type=PermissionType.SENSOR_VIEW))

        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['sensor_3'],
            permission_type=PermissionType.SENSOR_VIEW))

        # Custom role with a direct grant on sensor
        user_db = self.users['custom_role_sensor_grant']
        self.assertTrue(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['sensor_3'],
            permission_type=PermissionType.SENSOR_VIEW))

        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['sensor_3'],
            permission_type=PermissionType.SENSOR_ALL))


class ActionPermissionsResolverTestCase(BasePermissionsResolverTestCase):
    def setUp(self):
        super(ActionPermissionsResolverTestCase, self).setUp()

        # Create some mock users
        user_6_db = UserDB(name='1_role_action_pack_grant')
        user_6_db = User.add_or_update(user_6_db)
        self.users['custom_role_action_pack_grant'] = user_6_db

        user_7_db = UserDB(name='1_role_action_grant')
        user_7_db = User.add_or_update(user_7_db)
        self.users['custom_role_action_grant'] = user_7_db

        # Create some mock resources on which permissions can be granted
        action_1_db = ActionDB(pack='test_pack_1', name='action1', entry_point='',
                               runner_type={'name': 'run-local'})
        action_1_db = Action.add_or_update(action_1_db)
        self.resources['action_1'] = action_1_db

        action_2_db = ActionDB(pack='test_pack_1', name='action2', entry_point='',
                               runner_type={'name': 'run-local'})
        action_2_db = Action.add_or_update(action_1_db)
        self.resources['action_2'] = action_2_db

        action_3_db = ActionDB(pack='test_pack_2', name='action3', entry_point='',
                               runner_type={'name': 'run-local'})
        action_3_db = Action.add_or_update(action_3_db)
        self.resources['action_3'] = action_3_db

        # Create some mock roles with associated permission grants
        # Custom role 2 - one grant on parent pack
        # "action_view" on pack_1
        grant_db = PermissionGrantDB(resource_uid=self.resources['pack_1'].get_uid(),
                                     resource_type=ResourceType.PACK,
                                     permission_types=[PermissionType.ACTION_VIEW])
        grant_db = PermissionGrant.add_or_update(grant_db)
        permission_grants = [str(grant_db.id)]
        role_3_db = RoleDB(name='custom_role_action_pack_grant',
                           permission_grants=permission_grants)
        role_3_db = Role.add_or_update(role_3_db)
        self.roles['custom_role_action_pack_grant'] = role_3_db

        # Custom role 4 - one grant on action
        # "action_view" on action_3
        grant_db = PermissionGrantDB(resource_uid=self.resources['action_3'].get_uid(),
                                     resource_type=ResourceType.ACTION,
                                     permission_types=[PermissionType.ACTION_VIEW])
        grant_db = PermissionGrant.add_or_update(grant_db)
        permission_grants = [str(grant_db.id)]
        role_4_db = RoleDB(name='custom_role_action_grant', permission_grants=permission_grants)
        role_4_db = Role.add_or_update(role_4_db)
        self.roles['custom_role_action_grant'] = role_4_db

        # Create some mock role assignments
        user_db = self.users['custom_role_action_pack_grant']
        role_assignment_db = UserRoleAssignmentDB(
            user=user_db.name,
            role=self.roles['custom_role_action_pack_grant'].name)
        UserRoleAssignment.add_or_update(role_assignment_db)

        user_db = self.users['custom_role_action_grant']
        role_assignment_db = UserRoleAssignmentDB(user=user_db.name,
                                                  role=self.roles['custom_role_action_grant'].name)
        UserRoleAssignment.add_or_update(role_assignment_db)

    def test_user_has_resource_permission(self):
        resolver = ActionPermissionsResolver()

        # Admin user, should always return true
        resource_db = self.resources['action_1']
        user_db = self.users['admin']
        self.assertTrue(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=resource_db,
            permission_type=PermissionType.ACTION_DELETE))
        self.assertTrue(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=resource_db,
            permission_type=PermissionType.ACTION_EXECUTE))

        # Observer, should always return true for VIEW permission
        user_db = self.users['observer']
        self.assertTrue(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['action_1'],
            permission_type=PermissionType.ACTION_VIEW))
        self.assertTrue(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['action_2'],
            permission_type=PermissionType.ACTION_VIEW))

        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['action_1'],
            permission_type=PermissionType.ACTION_MODIFY))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['action_2'],
            permission_type=PermissionType.ACTION_DELETE))

        # No roles, should return false for everything
        user_db = self.users['no_roles']
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['action_1'],
            permission_type=PermissionType.ACTION_VIEW))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['action_2'],
            permission_type=PermissionType.ACTION_VIEW))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['action_1'],
            permission_type=PermissionType.ACTION_MODIFY))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['action_2'],
            permission_type=PermissionType.ACTION_DELETE))

        # Custom role with no permission grants, should return false for everything
        user_db = self.users['1_custom_role_no_permissions']
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['action_1'],
            permission_type=PermissionType.ACTION_VIEW))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['action_2'],
            permission_type=PermissionType.ACTION_VIEW))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['action_1'],
            permission_type=PermissionType.ACTION_MODIFY))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['action_2'],
            permission_type=PermissionType.ACTION_DELETE))

        # Custom role with unrelated permission grant to parent pack
        user_db = self.users['custom_role_pack_grant']
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['action_1'],
            permission_type=PermissionType.ACTION_VIEW))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['action_1'],
            permission_type=PermissionType.ACTION_EXECUTE))

        # Custom role with with grant on the parent pack
        user_db = self.users['custom_role_action_pack_grant']
        self.assertTrue(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['action_1'],
            permission_type=PermissionType.ACTION_VIEW))
        self.assertTrue(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['action_2'],
            permission_type=PermissionType.ACTION_VIEW))

        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['action_2'],
            permission_type=PermissionType.ACTION_EXECUTE))

        # Custom role with a direct grant on action
        user_db = self.users['custom_role_action_grant']
        self.assertTrue(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['action_3'],
            permission_type=PermissionType.ACTION_VIEW))

        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['action_2'],
            permission_type=PermissionType.ACTION_EXECUTE))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['action_3'],
            permission_type=PermissionType.ACTION_EXECUTE))


class RulePermissionsResolverTestCase(BasePermissionsResolverTestCase):
    def setUp(self):
        super(RulePermissionsResolverTestCase, self).setUp()

        # Create some mock users
        user_6_db = UserDB(name='1_role_rule_pack_grant')
        user_6_db = User.add_or_update(user_6_db)
        self.users['custom_role_rule_pack_grant'] = user_6_db

        user_7_db = UserDB(name='1_role_rule_grant')
        user_7_db = User.add_or_update(user_7_db)
        self.users['custom_role_rule_grant'] = user_7_db

        # Create some mock resources on which permissions can be granted
        rule_1_db = RuleDB(pack='test_pack_1', name='rule1')
        rule_1_db = Rule.add_or_update(rule_1_db)
        self.resources['rule_1'] = rule_1_db

        rule_2_db = RuleDB(pack='test_pack_1', name='rule2')
        rule_2_db = Rule.add_or_update(rule_2_db)
        self.resources['rule_2'] = rule_2_db

        rule_3_db = RuleDB(pack='test_pack_2', name='rule3')
        rule_3_db = Rule.add_or_update(rule_3_db)
        self.resources['rule_3'] = rule_3_db

        # Create some mock roles with associated permission grants
        # Custom role 2 - one grant on parent pack
        # "rule_view" on pack_1
        grant_db = PermissionGrantDB(resource_uid=self.resources['pack_1'].get_uid(),
                                     resource_type=ResourceType.PACK,
                                     permission_types=[PermissionType.RULE_VIEW])
        grant_db = PermissionGrant.add_or_update(grant_db)
        permission_grants = [str(grant_db.id)]
        role_3_db = RoleDB(name='custom_role_rule_pack_grant',
                           permission_grants=permission_grants)
        role_3_db = Role.add_or_update(role_3_db)
        self.roles['custom_role_rule_pack_grant'] = role_3_db

        # Custom role 4 - one grant on rule
        # "rule_view on rule_3
        grant_db = PermissionGrantDB(resource_uid=self.resources['rule_3'].get_uid(),
                                     resource_type=ResourceType.RULE,
                                     permission_types=[PermissionType.RULE_VIEW])
        grant_db = PermissionGrant.add_or_update(grant_db)
        permission_grants = [str(grant_db.id)]
        role_4_db = RoleDB(name='custom_role_rule_grant', permission_grants=permission_grants)
        role_4_db = Role.add_or_update(role_4_db)
        self.roles['custom_role_rule_grant'] = role_4_db

        # Create some mock role assignments
        user_db = self.users['custom_role_rule_pack_grant']
        role_assignment_db = UserRoleAssignmentDB(
            user=user_db.name,
            role=self.roles['custom_role_rule_pack_grant'].name)
        UserRoleAssignment.add_or_update(role_assignment_db)

        user_db = self.users['custom_role_rule_grant']
        role_assignment_db = UserRoleAssignmentDB(user=user_db.name,
                                                  role=self.roles['custom_role_rule_grant'].name)
        UserRoleAssignment.add_or_update(role_assignment_db)

    def test_user_has_resource_permission(self):
        resolver = RulePermissionsResolver()

        # Admin user, should always return true
        resource_db = self.resources['rule_1']
        user_db = self.users['admin']
        self.assertTrue(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=resource_db,
            permission_type=PermissionType.RULE_MODIFY))
        self.assertTrue(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=resource_db,
            permission_type=PermissionType.RULE_DELETE))

        # Observer, should always return true for VIEW permission
        user_db = self.users['observer']
        self.assertTrue(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['rule_1'],
            permission_type=PermissionType.RULE_VIEW))
        self.assertTrue(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['rule_2'],
            permission_type=PermissionType.RULE_VIEW))

        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['rule_1'],
            permission_type=PermissionType.RULE_MODIFY))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['rule_2'],
            permission_type=PermissionType.RULE_DELETE))

        # No roles, should return false for everything
        user_db = self.users['no_roles']
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['rule_1'],
            permission_type=PermissionType.RULE_VIEW))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['rule_2'],
            permission_type=PermissionType.RULE_VIEW))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['rule_3'],
            permission_type=PermissionType.RULE_DELETE))

        # Custom role with no permission grants, should return false for everything
        user_db = self.users['1_custom_role_no_permissions']
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['rule_1'],
            permission_type=PermissionType.RULE_VIEW))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['rule_2'],
            permission_type=PermissionType.RULE_VIEW))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['rule_3'],
            permission_type=PermissionType.RULE_DELETE))

        # Custom role with unrelated permission grant to parent pack
        user_db = self.users['custom_role_pack_grant']
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['rule_1'],
            permission_type=PermissionType.RULE_VIEW))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['rule_2'],
            permission_type=PermissionType.RULE_VIEW))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['rule_3'],
            permission_type=PermissionType.RULE_DELETE))


        # Custom role with with grant on the parent pack
        user_db = self.users['custom_role_rule_pack_grant']
        self.assertTrue(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['rule_1'],
            permission_type=PermissionType.RULE_VIEW))
        self.assertTrue(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['rule_2'],
            permission_type=PermissionType.RULE_VIEW))

        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['rule_1'],
            permission_type=PermissionType.RULE_DELETE))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['rule_2'],
            permission_type=PermissionType.RULE_MODIFY))

        # Custom role with a direct grant on rule
        user_db = self.users['custom_role_rule_grant']
        self.assertTrue(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['rule_3'],
            permission_type=PermissionType.RULE_VIEW))

        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['rule_3'],
            permission_type=PermissionType.RULE_ALL))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['rule_3'],
            permission_type=PermissionType.RULE_MODIFY))
        self.assertFalse(resolver.user_has_resource_permission(
            user_db=user_db,
            resource_db=self.resources['rule_3'],
            permission_type=PermissionType.RULE_DELETE))