# This file was generated with the assistance of an AI coding tool.
"""The server's own storage, apart from the IFC graph (IFC-LPG's F38 a, step two).

What OpenCDE is about, accounts, projects, documents and their versions, topics, and the server's own jobs, is the
server's data; a model's content is IFC-LPG's. The two meet by values only (a conversion names its model by id, a
component names its element by GlobalId), so that they can live in different databases: ``OPENCDE_STORE_GRAPH_URI``
names the server's own, and the IFC graph's connection is used when it is not set (F24 a). ``conversions`` holds the
first record kept here; the repositories of the other areas follow.
"""
