declare module "espeak-ng" {
  interface ESpeakEngine {
    FS: {
      readFile(path: string): Uint8Array;
    };
  }

  interface ESpeakOptions {
    arguments?: string[];
    locateFile?: (path: string, prefix: string) => string;
  }

  const createEngine: (options?: ESpeakOptions) => Promise<ESpeakEngine>;
  export default createEngine;
}

declare module "espeak-ng/dist/espeak-ng.wasm?url" {
  const url: string;
  export default url;
}
