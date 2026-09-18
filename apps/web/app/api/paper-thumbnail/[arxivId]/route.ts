import { readFile } from "node:fs/promises";
import { basename, dirname, join } from "node:path";

export const runtime = "nodejs";

const ARXIV_ID_PATTERN = /^\d{4}\.\d{4,5}(?:v[1-9]\d*)?$/;
const IMAGE_TYPES = [
  [".webp", "image/webp"],
  [".png", "image/png"],
  [".jpg", "image/jpeg"],
  [".jpeg", "image/jpeg"],
] as const;

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ arxivId: string }> },
) {
  const { arxivId } = await params;
  if (!ARXIV_ID_PATTERN.test(arxivId)) {
    return new Response(null, { status: 404 });
  }

  const workingDirectory = process.cwd();
  const runsFromWebDirectory =
    basename(workingDirectory) === "web" &&
    basename(dirname(workingDirectory)) === "apps";

  for (const [extension, contentType] of IMAGE_TYPES) {
    try {
      const imagePath = runsFromWebDirectory
        ? join(
            process.cwd(),
            "..",
            "..",
            "data",
            "paper-thumbnails",
            `${arxivId}${extension}`,
          )
        : join(
            process.cwd(),
            "data",
            "paper-thumbnails",
            `${arxivId}${extension}`,
          );
      const image = await readFile(imagePath);
      return new Response(new Uint8Array(image), {
        headers: { "Content-Type": contentType },
      });
    } catch {
      // Missing directories, missing files, and read failures all resolve to 404.
    }
  }

  return new Response(null, { status: 404 });
}
