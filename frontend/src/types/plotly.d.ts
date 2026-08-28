declare module 'plotly.js-dist-min' {
  interface Plotly {
    newPlot: (
      root: HTMLElement,
      data: unknown,
      layout?: Record<string, unknown>,
      config?: Record<string, unknown>,
    ) => Promise<unknown>
    purge: (root: HTMLElement) => void
    Plots: {
      resize: (root: HTMLElement) => void
    }
  }
  const Plotly: Plotly
  export default Plotly
}
