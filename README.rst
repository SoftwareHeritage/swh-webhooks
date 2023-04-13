Software Heritage - Webhooks
============================

Python package to manage Software Heritage Webhooks built on top of
the `Svix framework <https://docs.svix.com/>`__.

API Overview
------------

The webhooks framework for Software Heritage is based on three main concepts:

- ``event type``: named event and description of associated data
- ``endpoint``: URL to send events data
- ``event``: message sent to endpoints

Event type
^^^^^^^^^^

An event type defines an event and its JSON messages that are sent through webhooks.
It is composed of:

- a name in the form ``<group>.<event>``
- a description
- a `JSON schema <https://json-schema.org/>`__ describing the JSON payload
  sent to endpoints
