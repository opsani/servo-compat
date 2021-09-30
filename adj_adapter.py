"""
A servox add-on that captures 'adjust' events on before_event and modifies
them depending on what's found in the 'control' data, as follows:

if the event has non-empty control data and it contains userdata/deploy_to,
the list of adjustments in the 'adjust' event is trimmed to contain changes ONLY
to the component that matches the value of userdata/deploy_to.

In addition, if configured to do so, the 'after describe' event is captured and
the result is modified to make all settings in designated components appear 'pinned'
in the descriptor that is returned, but without making them 'pinned' in the ServoX
internal data structure - thus they can be modified with 'adjust'.
"""

# TODO: rename file and class

import asyncio

from typing import List  # Any, Dict, List, Optional

import pydantic
import servo
import servo.errors
import servo.connectors.kubernetes as k8s

from servo.events import current_event  # EventResult


class AdjustOnConfiguration(servo.BaseConfiguration):
    """configuration for the adjust adapter"""

    # TODO: is any config needed?

    enable: bool
    fake_pinned: List[str] = pydantic.Field(
        [],
        description="List of components to fake as 'pinned' in the 'DESCRIBE' reply."
    )

    @classmethod
    def generate(cls, **kwargs) -> "AdjustOnConfiguration":
        """generate a default configuration"""
        return cls(description="Set 'enable' to true to enable deploy_to filtering.", enable=False, **kwargs)


class AdjustFilterConnector(servo.BaseConnector):
    """the adjust_filter connector class"""

    config: AdjustOnConfiguration

    @servo.before_event(servo.Events.adjust)
    async def before_adjust(self, **kwargs) -> None:
        """adjust event hook"""
        if not self.config.enable:
            return
        event = current_event().event
        servo.logger.debug(f">>>> before adj: {event.name} {repr(kwargs)}")
        if not kwargs:
            return
        control = kwargs.get("control", None)
        if not control or not control.userdata:
            return

        # old k8s had 'adjust_on' setting with value containing an expression, to be
        # evaluated with globals={__builtins__:None} {"data":input}
        # formula looks like:
        # data["control"]["userdata"]["deploy_to"] == "canary"

        deploy_to = control.userdata.get("deploy_to")
        if not deploy_to:
            return

        # we have a non-empty deploy_to setting, clear all components other than
        # the one matching 'deploy_to from 'adjust' data

        adjustments = kwargs["adjustments"]  # list[Adjustment]
        adjustments[:] = filter(lambda a: a.component_name == deploy_to, adjustments)
        servo.logger.debug(f">>> new adjustments: {repr(adjustments)}")
        if not adjustments:
            servo.logger.warning(f"deploy_to={deploy_to} caused all adjustments to be dropped!")

    @servo.after_event(servo.Events.describe)
    def fixup_results(self, results: List[servo.EventResult]) -> None:
        fake_pinned = self.config.fake_pinned
        if not fake_pinned:
            return
        for result in results:
            description = result.value
            for comp in description.components:
                if comp.name not in fake_pinned:
                    continue
                for setting in comp.settings:
                    setting.pinned = True
