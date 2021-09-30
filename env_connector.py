"""
A servox add-on that is set up to be invoked before describe/adjust/measure events.
It checks whether the "current mode" annotation matches the optimization mode in the incoming event
and if it does not, it writes the mode found in the event into the 'desired mode' annotation.
If it does that, it also holds the execution of the 'pre' event handler to block the
execution of the command temporarily. It is expected that the annotation update will (eventually)
trigger a restart of servo, making the held command the last one that the running instance ever sees.

This add-on should be used only in conjunction with the 'kubernetes' connector as the handler of
'adjust' commands.
"""

import asyncio

# from typing import List  # Any, Dict, List, Optional

import pydantic
import servo
import servo.errors
import servo.connectors.kubernetes as k8s

from servo.events import current_event  # EventResult
import kubernetes_asyncio.client.exceptions  # for ApiException


class EnvironmentConfiguration(servo.BaseConfiguration):
    """configuration for the env. add-on"""

    current_mode_namespace: str = pydantic.Field(
        description="Namespace of the deployment where the 'current mode' annotation is",
    )
    current_mode_deployment_name: str = pydantic.Field(
        description="Name of the deployment where the 'current mode' annotation is"
    )
    current_mode_annotation: str = pydantic.Field(description="The current mode annotation")
    desired_mode_namespace: str = pydantic.Field(
        description="Namespace of the deployment where the 'desired mode' annotation is"
    )
    desired_mode_deployment_name: str = pydantic.Field(
        description="Namespace of the deployment where the 'desired mode' annotation is"
    )
    desired_mode_annotation: str = pydantic.Field(description="The desired mode annotation")

    @classmethod
    def generate(cls, **kwargs) -> "EnvironmentConfiguration":
        """generate a default configuration"""
        return cls(
            description="Update namespace and deployment names to match servo's own deployment and target app, respectively.",
            current_mode_namespace="opsani",
            current_mode_deployment_name="servo",
            current_mode_annotation="oko.opsani.com/opt_mode",
            desired_mode_namespace="default",
            desired_mode_deployment_name="app",
            desired_mode_annotation="oko.opsani.com/desired_mode",
            **kwargs,
        )


class K8sEnvConnector(servo.BaseConnector):
    """the k8s_env connector class"""

    config: EnvironmentConfiguration

    @servo.on_event()
    async def attach(self, servo_: servo.Servo) -> None:
        """connector initialization"""
        # should we use self.logger instead?
        servo.logger.debug(">>>> k8s_env(instance={self.name}) attached")
        # NOTE: if a specific instance of the k8s connector is needed,
        # this is the place to locate it
        # for c in servo_.connectors:
        #    servo.logger.debug(f">>>>    {c.name} ({dir(c)})")

    async def _check_env(self, desired_mode: str) -> None:
        """test if 'current mode' annotation matches the desired_mode arg.
        If not: write desired_mode into the 'desired mode' annotation target.
        This is intended to be called from the 'pre' handler of any events
        that should trigger environment change on desired!=current mismatch"""

        servo.logger.debug(f">>>> k8s_env check: desired mode = {desired_mode}")
        # if mode is empty: do nothing (see servo: exec_command())
        if not desired_mode:
            return

        config = self.config
        # TODO: what does k8s.Deployment.read() do if the deployment was not found?
        try:
            current_dep = await k8s.Deployment.read(config.current_mode_deployment_name, config.current_mode_namespace)
        except kubernetes_asyncio.client.exceptions.ApiException as x:
            raise servo.errors.EventCancelledError(
                message=f"Failed to read deployment with current-mode annotation: {str(x)}"
            )
        current_ann = current_dep.obj.metadata.annotations
        if not current_ann:
            servo.logger.debug("NO ANNOTATIONS in 'current' deployment")
            return
        current_mode = current_ann.get(config.current_mode_annotation, None)
        if not current_mode:
            servo.logger.debug("current mode annotation missing/empty")
            return
        servo.logger.debug(f"current mode annotation: {current_mode}")

        if current_mode == desired_mode:
            return

        # mode differs, write an annotation into the deployment defined by 'desired_mode_*' settings
        # and block (our process should be killed shortly after the annotation update is detected)
        servo.logger.debug(f"mode is {current_mode}, desired mode is {desired_mode}, updating target")
        try:
            target_dep = await k8s.Deployment.read(config.desired_mode_deployment_name, config.desired_mode_namespace)
        except kubernetes_asyncio.client.exceptions.ApiException as x:
            raise servo.errors.EventCancelledError(
                message=f"Failed to read deployment with desired-mode annotation: {str(x)}"
            )

        if target_dep.obj.metadata.annotations is None:
            target_dep.obj.metadata.annotations = {}
        if target_dep.obj.metadata.annotations.get(config.desired_mode_annotation) == desired_mode:
            # TODO: what is the correct action when the annotation is already what we want it to be (should not be happening)
            servo.logger.warning(
                f"current mode={current_mode}, desired={desired_mode}, but target annotation is already set to {desired_mode}"
            )
        else:
            target_dep.obj.metadata.annotations[config.desired_mode_annotation] = desired_mode
            try:
                await target_dep.patch()
            except kubernetes_asyncio.client.exceptions.ApiException as x:
                raise servo.errors.EventCancelledError(message=f"Failed to write desired-mode annotation: {str(x)}")

        # block the command
        await asyncio.sleep(1200)  # TODO: configurable? NOTE: servox kills this quicker than the timeout here
        # if we're not killed yet and we get here, write a log message
        servo.logger.error("No restart after environment annotation update.")
        raise servo.errors.EventCancelledError

    @staticmethod
    def _get_desired_mode(args: dict) -> str:
        if not args:
            return None
        control = args.get("control", None)
        if not control:
            return None
        # assert isinstance(control, api.Control)
        if not control.environment:
            servo.logger.debug(f">>>> ENV: control.environment is {repr(control.environment)}")
            return None
        return control.environment.get("mode")

    @servo.before_event(servo.Events.measure)
    async def before_measure(self, **kwargs) -> None:
        """measure event hook"""
        event = current_event().event
        servo.logger.debug(f">>>> ENV before meas: {event.name} {repr(kwargs)}")
        mode = self._get_desired_mode(kwargs)
        await self._check_env(mode)

    @servo.before_event(servo.Events.describe)
    async def before_describe(self, **kwargs) -> None:
        """describe event hook"""
        event = current_event().event
        servo.logger.debug(f">>>> ENV before desc: {event.name} {repr(kwargs)}")
        mode = self._get_desired_mode(kwargs)
        await self._check_env(mode)

    @servo.before_event(servo.Events.adjust)
    async def before_adjust(self, **kwargs) -> None:
        """adjust event hook"""
        event = current_event().event
        servo.logger.debug(f">>>> ENV before adj: {event.name} {repr(kwargs)}")
        mode = self._get_desired_mode(kwargs)
        await self._check_env(mode)
