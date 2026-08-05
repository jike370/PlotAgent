import fs from "node:fs/promises";
import path from "node:path";

const outputDir = path.resolve("tests/fixtures/import/files");
await fs.mkdir(outputDir, { recursive: true });

const utf8Fixtures = {
  "csv_basic.csv": "time,signal\n0,1.5\n1,2.5\n",
  "csv_decimal_comma.csv": "time;signal\n0;1,5\n1;2,5\n",
  "tsv_zero_false.tsv": "index\tvalue\tvalid\n0\t0\tFalse\n1\t2\tTrue\n",
  "txt_metadata.txt":
    "Instrument: Spectrometer\nOperator: Test\ntime,signal\n0,1\n1,2\nEnd of export\n",
  "txt_multi_block.txt":
    "Instrument=Scope\nx,y\n0,1\n1,2\n\nx,y\n2,3\n3,4\nEnd\n",
  "csv_nonfinite.csv": "x,y\n0,NaN\n1,Inf\n2,-Inf\n3,NA\n",
  "csv_quoted.csv": '"sample,name",value\nA,1\nB,2\n',
  "csv_utf8_bom.csv": "\ufefftime,value\n0,1\n1,2\n",
  "dat_pipe.dat": "time|response\n0|1.2\n1|2.4\n",
  "csv_numeric_no_header.csv": "0,1.5\n1,2.5\n2,3.5\n",
  "txt_channel_sweep.txt":
    "Channel: A\nSweep: 3\ntime,value\n0,1\n1,2\n",
  "csv_unicode_header.csv": "Cafe\u0301,Value\nA,1\nB,2\n",
  "txt_postamble.txt": "x,y\n0,1\n1,2\nCompleted normally\nChecksum OK\n",
  "clarify_delimiter.txt": "a,b;c\n1,2;3\n",
  "clarify_header.csv": "alpha,beta\ngroup-a,group-b\n1,2\n",
  "clarify_decimal.txt": "x;y\n0;1,5\n1;2.5\n",
  "reject_duplicate.csv": "Signal, Signal \n1,2\n3,4\n",
  "reject_no_data.txt": "Instrument: Empty\nNo measurements recorded\n",
  "reject_ragged.csv": "a,b,c\n1,2,3\n4,5\n",
  "reject_unsupported.json": '{"x": [1, 2]}\n',
};

for (const [name, contents] of Object.entries(utf8Fixtures)) {
  await fs.writeFile(path.join(outputDir, name), contents, "utf8");
}

await fs.writeFile(
  path.join(outputDir, "csv_utf16le.csv"),
  Buffer.concat([Buffer.from([0xff, 0xfe]), Buffer.from("time,value\n0,1\n1,2\n", "utf16le")]),
);
await fs.writeFile(
  path.join(outputDir, "csv_cp1252.csv"),
  Buffer.from("Temp\u00e9rature,Value\n20,1\n21,2\n", "latin1"),
);
await fs.writeFile(
  path.join(outputDir, "reject_binary.csv"),
  Buffer.from([0x61, 0x62, 0x63, 0x00, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6a, 0x6b]),
);
