-- This file was generated with the assistance of an AI coding tool.
-- The BCF area (ADR 0029): topics and what hangs off them (related topics, header files, document references, the
-- BIM snippet), comments, viewpoints with their components and bitmaps, the project's BCF documents, and the topic
-- and comment events. A topic and all of its own go with its project; its events stay until the project goes.
-- Text that is filtered or ordered on is COLLATE "C", by code point, as the graphs order it.

-- The topic's counter for server_assigned_id is projects.topic_counter (0001). The BIM snippet is four columns, and
-- three more when its file was uploaded.
CREATE TABLE topics (
    guid text PRIMARY KEY,
    project_id text NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    title text COLLATE "C" NOT NULL,
    description text COLLATE "C",
    server_assigned_id text COLLATE "C" NOT NULL,
    creation_date iso_utc COLLATE "C" NOT NULL,
    creation_author text COLLATE "C" NOT NULL,
    modified_date iso_utc COLLATE "C",
    modified_author text COLLATE "C",
    topic_type text COLLATE "C",
    topic_status text COLLATE "C",
    priority text COLLATE "C",
    "index" integer,
    labels text[] COLLATE "C",
    reference_links text[],
    assigned_to text COLLATE "C",
    stage text COLLATE "C",
    due_date iso_utc COLLATE "C",
    snippet_type text,
    snippet_is_external boolean,
    snippet_reference text,
    snippet_reference_schema text,
    snippet_storage_key text,
    snippet_filename text,
    snippet_size bigint
);
CREATE INDEX topics_project ON topics (project_id);
CREATE INDEX topics_creation_date ON topics (project_id, creation_date, server_assigned_id);
CREATE INDEX topics_modified_date ON topics (project_id, modified_date);

-- RELATED_TO (BCF 3.6): either topic's deletion takes the link.
CREATE TABLE related_topics (
    topic_guid text NOT NULL REFERENCES topics (guid) ON DELETE CASCADE,
    related_guid text NOT NULL REFERENCES topics (guid) ON DELETE CASCADE,
    PRIMARY KEY (topic_guid, related_guid)
);
CREATE INDEX related_topics_related ON related_topics (related_guid);

-- The models a topic's header names (BCF 3.3.2), in their order.
CREATE TABLE header_files (
    id text PRIMARY KEY,
    topic_guid text NOT NULL REFERENCES topics (guid) ON DELETE CASCADE,
    position integer NOT NULL,
    ifc_project text,
    ifc_spatial_structure_element text,
    filename text,
    date iso_utc,
    reference text
);
CREATE INDEX header_files_topic ON header_files (topic_guid, position);

-- document_guid names a BCF document or a Documents API document of the project (BCF 3.7.2), checked on writing.
CREATE TABLE document_references (
    guid text PRIMARY KEY,
    topic_guid text NOT NULL REFERENCES topics (guid) ON DELETE CASCADE,
    document_guid text,
    url text,
    description text,
    created_at iso_utc COLLATE "C" NOT NULL
);
CREATE INDEX document_references_topic ON document_references (topic_guid);

-- viewpoint_guid and reply_to_comment_guid are checked on writing, as in the graph, which has no link for them.
CREATE TABLE comments (
    guid text PRIMARY KEY,
    topic_guid text NOT NULL REFERENCES topics (guid) ON DELETE CASCADE,
    date iso_utc COLLATE "C" NOT NULL,
    author text COLLATE "C" NOT NULL,
    comment text NOT NULL,
    viewpoint_guid text,
    reply_to_comment_guid text,
    modified_date iso_utc,
    modified_author text
);
CREATE INDEX comments_topic ON comments (topic_guid, date);
CREATE INDEX comments_viewpoint ON comments (topic_guid, viewpoint_guid);

-- Viewpoints are immutable (BCF 3.5.2). The camera, the lines and the clipping planes are the same JSON text as the
-- graph's, opaque geometry; storage_key is the snapshot's file.
CREATE TABLE viewpoints (
    guid text PRIMARY KEY,
    topic_guid text NOT NULL REFERENCES topics (guid) ON DELETE CASCADE,
    "index" integer,
    author text NOT NULL,
    creation_date iso_utc COLLATE "C" NOT NULL,
    camera_kind text CHECK (camera_kind IN ('orthogonal', 'perspective')),
    camera text,
    lines text,
    clipping_planes text,
    snapshot_type text,
    storage_key text,
    has_components boolean NOT NULL,
    default_visibility boolean NOT NULL,
    has_hints boolean NOT NULL,
    spaces_visible boolean,
    space_boundaries_visible boolean,
    openings_visible boolean
);
CREATE INDEX viewpoints_topic ON viewpoints (topic_guid, creation_date);

-- Selection, coloring (one group per color) and the visibility's exceptions; gtin is copied on from the models by
-- the IFC-DB service.
CREATE TABLE components (
    id text PRIMARY KEY,
    viewpoint_guid text NOT NULL REFERENCES viewpoints (guid) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('selection', 'coloring', 'exception')),
    group_index integer NOT NULL,
    position integer NOT NULL,
    color text,
    ifc_guid text,
    originating_system text,
    authoring_tool_id text,
    gtin text
);
CREATE INDEX components_viewpoint ON components (viewpoint_guid, role, group_index, position);
CREATE INDEX components_ifc_guid ON components (ifc_guid);

CREATE TABLE bitmaps (
    guid text PRIMARY KEY,
    viewpoint_guid text NOT NULL REFERENCES viewpoints (guid) ON DELETE CASCADE,
    position integer NOT NULL,
    bitmap_type text NOT NULL,
    storage_key text NOT NULL,
    height double precision NOT NULL,
    loc_x double precision NOT NULL,
    loc_y double precision NOT NULL,
    loc_z double precision NOT NULL,
    nrm_x double precision NOT NULL,
    nrm_y double precision NOT NULL,
    nrm_z double precision NOT NULL,
    up_x double precision NOT NULL,
    up_y double precision NOT NULL,
    up_z double precision NOT NULL
);
CREATE INDEX bitmaps_viewpoint ON bitmaps (viewpoint_guid, position);

-- Files uploaded through the BCF API (3.8); the client's file name is never a path.
CREATE TABLE bcf_documents (
    guid text PRIMARY KEY,
    project_id text NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    filename text NOT NULL,
    storage_key text NOT NULL,
    size bigint NOT NULL,
    created_at iso_utc COLLATE "C" NOT NULL,
    author text NOT NULL
);
CREATE INDEX bcf_documents_project ON bcf_documents (project_id, created_at);

-- BCF 3.9 and 3.10: one event per change, its actions as parallel lists. An event belongs to the project, so that
-- it outlives its topic.
CREATE TABLE bcf_events (
    id text PRIMARY KEY,
    project_id text NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    kind text NOT NULL CHECK (kind IN ('topic', 'comment')),
    topic_guid text COLLATE "C" NOT NULL,
    comment_guid text COLLATE "C",
    author text COLLATE "C" NOT NULL,
    date iso_utc COLLATE "C" NOT NULL,
    action_types text[] COLLATE "C" NOT NULL,
    action_values text[] NOT NULL
);
CREATE INDEX bcf_events_project ON bcf_events (project_id, kind, date);
CREATE INDEX bcf_events_topic ON bcf_events (topic_guid, date);

-- What the BCF area reads of the jobs area (0005 defines them anew): the files of a topic's trials of change sets,
-- which go with the topic, and the IFC project of a finished conversion of a document's version.
CREATE VIEW proposal_files (topic_guid, storage_key) AS
    SELECT NULL::text, NULL::text WHERE false;
CREATE VIEW conversion_ifc_projects (document_id, version_index, ifc_project_guid) AS
    SELECT NULL::text, NULL::integer, NULL::text WHERE false;

-- The files the BCF area holds for a project: snippets, snapshots, bitmaps, BCF documents and the trials' files.
CREATE VIEW bcf_files (project_id, storage_key) AS
    SELECT t.project_id, t.snippet_storage_key FROM topics t WHERE t.snippet_storage_key IS NOT NULL
    UNION ALL
    SELECT t.project_id, v.storage_key FROM viewpoints v JOIN topics t ON t.guid = v.topic_guid
    WHERE v.storage_key IS NOT NULL
    UNION ALL
    SELECT t.project_id, b.storage_key
    FROM bitmaps b JOIN viewpoints v ON v.guid = b.viewpoint_guid JOIN topics t ON t.guid = v.topic_guid
    UNION ALL
    SELECT d.project_id, d.storage_key FROM bcf_documents d
    UNION ALL
    SELECT t.project_id, f.storage_key FROM proposal_files f JOIN topics t ON t.guid = f.topic_guid
    WHERE f.storage_key IS NOT NULL;

-- Every file a project owns (0001), so that deleting it frees the disk too: the Documents area's (0003) and BCF's.
CREATE OR REPLACE VIEW project_files (project_id, storage_key) AS
    SELECT project_id, storage_key FROM document_files
    UNION ALL
    SELECT project_id, storage_key FROM bcf_files;
