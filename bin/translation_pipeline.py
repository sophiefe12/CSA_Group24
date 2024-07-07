#!/usr/bin/env python3
import os
import sys

# Ensure the lib directory is in the module search path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'lib'))

from aws_cdk import App
from translation_pipeline_stack import TranslationPipelineStack

app = App()
TranslationPipelineStack(app, "TranslationPipelineStack")

app.synth()
