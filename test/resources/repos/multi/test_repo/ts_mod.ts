// TypeScript module for testing multi-language support

export interface TsInterface {
    name: string;
    value: number;
}

export class TsClass {
    private data: string;
    
    constructor(data: string) {
        this.data = data;
    }
    
    getData(): string {
        return this.data;
    }
}

export function ts_func(): string {
    return "ts";
}

export function anotherTsFunc(param: number): number {
    return param * 3;
}

export const TS_CONSTANT = "typescript_constant";
