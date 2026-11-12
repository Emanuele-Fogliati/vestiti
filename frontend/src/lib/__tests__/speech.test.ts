import { describe, expect, it } from "vitest";
import { secureAddress } from "../speech";

const at = (protocol: string, hostname: string) => ({ protocol, hostname, pathname: "/start", search: "?x=1", hash: "#own" });

describe("secureAddress", () => {
  it("sends a phone on the home network to the https port", () => {
    expect(secureAddress(at("http:", "192.168.1.20"), false)).toBe("https://192.168.1.20:8443/start?x=1#own");
  });
  it("leaves secure pages alone", () => {
    expect(secureAddress(at("http:", "localhost"), true)).toBeNull();
    expect(secureAddress(at("https:", "192.168.1.20"), true)).toBeNull();
  });
});
