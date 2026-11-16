declare module "latex.js" {
  export class HtmlGenerator {
    constructor(options?: {
      hyphenate?: boolean;
      CustomMacros?: { new (): object; symbols?: Map<string, string> };
    });
    domFragment(): DocumentFragment;
  }

  export function parse(
    source: string,
    options: { generator: HtmlGenerator },
  ): HtmlGenerator;
}
