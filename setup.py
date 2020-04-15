from setuptools import find_packages, setup

try:  # for pip >= 10
    from pip._internal.req import parse_requirements
except ImportError:  # for pip <= 9.0.3
    from pip.req import parse_requirements

requirements = parse_requirements("requirements.txt", session=False)


setup(
    name='manuka',
    version='0.1.0',
    description=('User management for the Nectar Research Cloud'),
    author='Sam Morrison',
    author_email='sorrison@gmail.com',
    url='https://github.com/NeCTAR-RC/manuka',
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'manuka-worker = manuka.cmd.worker:main',
            'manuka-api = manuka.cmd.api:main',
            'manuka-manage = manuka.cmd.manage:cli',
        ],
    },
    include_package_data=True,
    install_requires=[str(r.req) for r in requirements],
    license="Apache",
    zip_safe=False,
)
