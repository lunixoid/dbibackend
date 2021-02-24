#!/usr/bin/python3

from setuptools import setup, find_packages
import dbibackend


setup(
    name='dbibackend',
    version=dbibackend.__version__,
    packages=find_packages(),
    author='Kalashnikov Roman',
    author_email='lunix0x@gmail.com',
    license='MIT',
    classifiers=[
        'Programming Language :: Python :: 3.7',
    ],
    entry_points={
        'console_scripts': [
            'dbibackend = dbibackend.dbibackend:main'
            ]
    },
    install_requires=[
        'pyusb==1.1.0',
        'usb==0.0.83.dev0'
    ]
)
