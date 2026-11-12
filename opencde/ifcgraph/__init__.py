# This file was generated with the assistance of an AI coding tool.
"""IFC-LPG: uploaded IFC models as graph data, so BCF components can be joined to building elements.

Optional (``OPENCDE_IFC_DB_ENABLED``, extra ``ifc-lpg`` for IfcOpenShell). The
conversion runs in a separate worker process with time and memory limits;
the result is imported in batches; viewpoint components get the GTIN of the
element they name, looked up in the model by ``GlobalId``.
"""
