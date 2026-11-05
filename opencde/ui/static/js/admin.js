// Entry module of the admin pages: progressive enhancement only.
import { enhanceConfirmations } from "./confirm.js";
import { enhanceCopyButtons } from "./copy.js";
import { enhanceTables } from "./table.js";

enhanceTables();
enhanceConfirmations();
enhanceCopyButtons();
