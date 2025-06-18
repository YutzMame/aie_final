#!/usr/bin/env python3
import os

import aws_cdk as cdk

from qa_system.qa_system_stack import QaSystemStack

env_us = cdk.Environment(account="922058108332", region="us-east-1")

app = cdk.App()
QaSystemStack(app, "QaSystemStack", env=env_us)

app.synth()
