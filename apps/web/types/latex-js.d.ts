declare module "latex.js" {
  export class HtmlGenerator {
    constructor(options?: { hyphenate?: boolean });
    domFragment(): DocumentFragment;
  }

  export function parse(
    source: string,
    options: { generator: HtmlGenerator },
  ): HtmlGenerator;
}
