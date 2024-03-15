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


Endpoint
^^^^^^^^

An endpoint is defined by an HTTP URL where events and their JSON data are sent to.
An endpoint is created for a specific event type and an optional channel (each event
type has its own list of endpoints).

Channels are an extra dimension of filtering events that is orthogonal to event types.
Events are sent (or not sent) to endpoints based on the following conditions:

- Endpoint has no channel set: this is a catch-all, all events are sent to it,
  regardless of whether the event had a channel set.
- Both endpoint and event have a channel set: if there's the same, the event is sent
  to the endpoint.
- Endpoint has a channel set and event has no channel set: the event is not sent to
  the endpoint.

Event
^^^^^

An event of a given type can be sent with a JSON payload, its delivery will be attempted
to all endpoints listening to the event type.

If the JSON payload does not match the JSON schema of the event type, an error is raised.

Event can optionally be sent on a specific channel orthogonal to the event type, the
conditions of its delivery is detailed in the previous section.
