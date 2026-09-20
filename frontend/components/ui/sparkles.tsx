"use client";
import React, { useId } from "react";
import { useEffect, useState } from "react";
import Particles, { initParticlesEngine } from "@tsparticles/react";
import type { Container } from "@tsparticles/engine";
import { loadSlim } from "@tsparticles/slim";
import { cn } from "@/lib/utils";
import { motion, useAnimation } from "framer-motion";

type ParticlesProps = {
  id?: string;
  className?: string;
  background?: string;
  minSize?: number;
  maxSize?: number;
  speed?: number;
  particleColor?: string;
  particleDensity?: number;
};

/**
 * Ported from the standard SparklesCore. Defaults changed from the
 * original blue/white to LiftGuard's brand violet, and density brought
 * down substantially (1200 -> 60) — this is a clinical dashboard, not a
 * marketing landing page, so the effect needs to read as "subtle
 * instrument shimmer" behind a heading, not a confetti burst.
 */
export const SparklesCore = (props: ParticlesProps) => {
  const {
    id,
    className,
    background,
    minSize,
    maxSize,
    speed,
    particleColor,
    particleDensity,
  } = props;
  const [init, setInit] = useState(false);

  useEffect(() => {
    initParticlesEngine(async (engine) => {
      await loadSlim(engine);
    }).then(() => {
      setInit(true);
    });
  }, []);

  const controls = useAnimation();

  const particlesLoaded = async (container?: Container) => {
    if (container) {
      controls.start({
        opacity: 1,
        transition: { duration: 1 },
      });
    }
  };

  const generatedId = useId();

  return (
    <motion.div animate={controls} className={cn("opacity-0", className)}>
      {init && (
        <Particles
          id={id || generatedId}
          className="h-full w-full"
          particlesLoaded={particlesLoaded}
          options={{
            background: {
              color: { value: background || "transparent" },
            },
            fullScreen: { enable: false, zIndex: 1 },
            fpsLimit: 90,
            interactivity: {
              events: {
                onClick: { enable: false, mode: "push" },
                onHover: { enable: false, mode: "repulse" },
                // tsparticles v3: resize is an IResizeEvent object, not a boolean
                resize: { enable: true },
              },
              modes: {
                push: { quantity: 2 },
                repulse: { distance: 150, duration: 0.4 },
              },
            },
            particles: {
              color: { value: particleColor || "#7C5CFF" },
              move: {
                enable: true,
                direction: "none",
                speed: { min: 0.05, max: 0.3 },
                random: false,
                straight: false,
                outModes: { default: "out" },
              },
              number: {
                density: { enable: true, width: 400, height: 400 },
                value: particleDensity ?? 60,
              },
              opacity: {
                value: { min: 0.1, max: 0.6 },
                animation: {
                  enable: true,
                  speed: speed || 2,
                  sync: false,
                  startValue: "random",
                  destroy: "none",
                },
              },
              shape: { type: "circle" },
              size: {
                value: { min: minSize || 0.4, max: maxSize || 1.2 },
              },
            },
            detectRetina: true,
          }}
        />
      )}
    </motion.div>
  );
};
