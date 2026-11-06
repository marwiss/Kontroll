// Entry module of the admin pages: progressive enhancement only.
import { enhanceConfirmations } from "./confirm.js";
import { enhanceCopyButtons } from "./copy.js";
import { enhanceInlineForms } from "./inline.js";
import { enhanceTables } from "./table.js";

function enhance(root) {
  enhanceTables(root);
  enhanceConfirmations(root);
  enhanceCopyButtons(root);
}

enhance(document);
enhanceInlineForms(enhance);
