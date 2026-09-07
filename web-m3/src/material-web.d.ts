// Material Web ships as plain custom elements (Lit), not React components,
// so TSX doesn't know about them by default. React 19 supports custom
// elements natively (property vs. attribute handling included) -- this
// just tells TypeScript the tag names exist and roughly what props they
// take, loosely, since these are the only ones this app uses.
import type { DetailedHTMLProps, HTMLAttributes } from "react";

type MdProps = DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement> & {
  [prop: string]: unknown;
};

// React 19 moved JSX types inside the "react" module itself (the bare
// global `JSX` namespace augmentation that worked pre-19 no longer does)
// -- this is the current documented way to extend IntrinsicElements.
declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      "md-filled-button": MdProps;
      "md-outlined-button": MdProps;
      "md-text-button": MdProps;
      "md-icon-button": MdProps;
      "md-checkbox": MdProps;
      "md-outlined-select": MdProps;
      "md-select-option": MdProps;
      "md-outlined-text-field": MdProps;
      "md-slider": MdProps;
      "md-filled-card": MdProps;
      "md-outlined-card": MdProps;
      "md-navigation-drawer-modal": MdProps;
      "md-elevation": MdProps;
      "md-icon": MdProps;
    }
  }
}
