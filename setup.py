#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import setuptools

from pbr.packaging import parse_requirements


setuptools.setup(
    name='manuka',
    version='2.0.0',
    description=('User management for the Nectar Research Cloud'),
    author='Sam Morrison',
    author_email='sorrison@gmail.com',
    url='https://github.com/NeCTAR-RC/manuka',
    packages=setuptools.find_packages(),
    entry_points={
        'console_scripts': [
            'manuka-worker = manuka.cmd.worker:main',
            'manuka-api = manuka.cmd.api:main',
            'manuka-manage = manuka.cmd.manage:cli',
        ],
        'oslo.config.opts': [
            'manuka = manuka.config:list_opts',
        ],
        'oslo.policy.policies': [
            'manuka = manuka.common.policies:list_rules',
        ],
        'oslo.policy.enforcer': [
            'manuka = manuka.policy:get_enforcer',
        ],
    },
    include_package_data=True,
    setup_requires=['pbr>=3.0.0'],
    install_requires=parse_requirements(),
    license="Apache",
    zip_safe=False,
)
